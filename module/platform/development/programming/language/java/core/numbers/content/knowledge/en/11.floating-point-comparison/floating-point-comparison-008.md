# Comparing with Relative Error in Java

## 1. Why Is Comparing `double` with `==` Often Not Enough?

For integers, the `==` comparison is usually the right choice to check whether two values are equal. For `float` and `double`, the result of a floating-point operation can **differ slightly from the ideal value** because only a finite number of binary values can be represented. For example:

~~~java
double computed = 0.1 + 0.2;
double expected = 0.3;

System.out.println(computed);            // 0.30000000000000004
System.out.println(computed == expected); // false
~~~

This is an illustrative snippet, not a standalone program. The `==` operator **is not wrong**: it answers whether the two current `double` values are equal according to floating-point comparison rules. The issue is that many real-world problems want to answer **"are two results close enough to each other within an acceptable error level?"**.

One way to quantify closeness is **relative error/tolerance**, which uses the ratio of the difference to the magnitude of the compared values. It is especially useful when quantities vary across many orders of magnitude.

For example:

- A difference of **1** between 1,000,000 and 1,000,001 is only about **0.0001%**.
- A difference of **1** between 1 and 2 is **50% or 100%**, depending on the reference chosen.

The same absolute error `1` does not carry the same meaning when the value scale changes dramatically. That is why relative error is used.

**Scope note:** this lesson explains **approximate arithmetic comparison**. It does not change the rules of `==`, does not make `double` operations exact, and does not replace domain-specific error standards.

## 2. Absolute Error and Relative Error

### Absolute Error

For two finite values `a` and `b`, absolute error is usually defined as:

\[
E_{\mathrm{abs}} = |a-b|
\]

If `a=1000000.0` and `b=1000000.5`, the absolute error is `0.5`. An approximate check using an absolute threshold is:

~~~java
Math.abs(a - b) <= absoluteTolerance
~~~

The line above is just an illustrative expression. It fits when the problem specifies error in **concrete units**: for example, measurement error at most 0.001 meters.

However, if `a` and `b` are sometimes around `1e-12` and sometimes around `1e12`, a single absolute threshold can be too loose at small scales and too strict at large scales.

### Relative Error Against a Reference

If `reference` is a **non-zero** standard value, relative error can be defined as:

\[
E_{\mathrm{rel,ref}} =
\frac{|observed-reference|}{|reference|}
\]

This is a sensible definition in measurements: the denominator is the magnitude of the **standard value**. For example, an error of `0.5` relative to `1_000_000` equals `0.0000005`, or `0.00005%`. With a threshold `relativeTolerance = 1e-6` (one part per million), the two numbers are considered close enough.

**A `reference == 0` denominator makes the formula undefined.** Do not silently replace a zero denominator with an arbitrary number without documenting the problem's policy.

### Symmetric Relative Error

If neither value is privileged as the "standard," you can choose a symmetric scale:

\[
scale = \max(|a|,|b|)
\]

\[
E_{\mathrm{rel,sym}} =
\frac{|a-b|}{\max(|a|,|b|)}
\quad \text{(when }scale>0\text{)}
\]

This lesson uses the **symmetric `max(|a|, |b|)`** variant in its main examples. Swapping `a` and `b` does not change the result. This formula is not the only definition of "relative error": some references use `|reference|`, the average magnitude, or a predefined physical scale. Agree on the **denominator** when designing APIs and writing tests.

### Percentages and Thresholds

| Threshold value `relTol` | Equivalent percentage | Meaning |
|---:|---:|---|
| `1e-2` | `1%` | Allows a difference of about one percent of the scale |
| `1e-3` | `0.1%` | About one part per thousand |
| `1e-6` | `0.0001%` | About one part per million |
| `1e-9` | `0.0000001%` | About one part per billion |

The threshold is an **application policy**, not a Java number that is "right for every `double`." Input data accuracy, the algorithm, number of calculation steps, units of measurement, and the consequences of a false positive all influence the appropriate threshold.

## 3. The Relative Comparison Formula and Two Things to Handle

An idealized check is often written:

\[
|a-b| \le relTol\cdot\max(|a|,|b|)
\]

or dividing both sides by a positive `scale`:

\[
\frac{|a-b|}{scale} \le relTol
\]

Assume `relTol` lies in `[0, 1)` so that "two numbers must actually be close" makes sense when both are finite.

**However, do not copy the formula directly while ignoring edge cases**:

1. **Both equal to 0:** `scale == 0`, so division produces `0.0 / 0.0`, which is `NaN`; without handling it beforehand, the comparison returns `false` even though the numbers are equal.
2. **Two very large finite numbers with opposite signs:** `a-b` can overflow to `Infinity`, even though `a` and `b` are individually finite. When `relTol < 1`, two numbers of opposite signs cannot be close enough under a pure relative rule (except both being 0, already handled).
3. **`NaN` or infinity:** you must explicitly decide how to interpret closeness; applying the formula's division mechanically can return `NaN` or unhelpful results.
4. **Numbers near 0:** one value of 0 and a very small positive value have a symmetric relative error of `1`, so they are **not** considered close if `relTol < 1`. The problem may need a separate **absolute threshold** near 0.

Adding these checks keeps the example stable across Java's `double` domain.

## 4. Implementing **Pure Relative** Comparison in Java 17+

Create the file `RelativeErrorDemo.java`:

~~~java
public class RelativeErrorDemo {
    /**
     * Nearly equal by symmetric ratio max(abs(a), abs(b)).
     * Policy: NaN differs from every value; infinities of the same sign are equal.
     * Tolerance must be finite and in [0, 1).
     */
    static boolean nearlyEqualRelative(double a, double b, double relTol) {
        if (!Double.isFinite(relTol) || relTol < 0.0 || relTol >= 1.0) {
            throw new IllegalArgumentException("invalid relative tolerance");
        }

        if (Double.isNaN(a) || Double.isNaN(b)) {
            return false;
        }
        if (a == b) {
            return true; // includes +0.0/-0.0 and infinities of the same sign
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }

        // With relTol < 1, two numbers with opposite signs or one equal to 0
        // cannot satisfy a pure relative error condition.
        if (a == 0.0 || b == 0.0 || ((a < 0.0) != (b < 0.0))) {
            return false;
        }

        // Two finite numbers with the same sign: subtraction does not overflow to infinity.
        double scale = Math.max(Math.abs(a), Math.abs(b));
        double relativeError = Math.abs(a - b) / scale;
        return relativeError <= relTol;
    }

    public static void main(String[] args) {
        System.out.println("largeLoose="
                + nearlyEqualRelative(1_000_000.0, 1_000_000.5, 1e-6));
        System.out.println("largeTight="
                + nearlyEqualRelative(1_000_000.0, 1_000_000.5, 1e-7));
        System.out.println("tiny="
                + nearlyEqualRelative(1e-12, 1.01e-12, 0.02));
        System.out.println("zeroVsTiny="
                + nearlyEqualRelative(0.0, 1e-12, 0.02));
        System.out.println("signedZero="
                + nearlyEqualRelative(0.0, -0.0, 0.0));
        System.out.println("oppositeLarge="
                + nearlyEqualRelative(
                        Double.MAX_VALUE, -Double.MAX_VALUE, 0.5));
        System.out.println("sameInfinity="
                + nearlyEqualRelative(
                        Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, 1e-6));
        System.out.println("notANumber="
                + nearlyEqualRelative(Double.NaN, Double.NaN, 1e-6));
    }
}
~~~

Compile and run:

~~~bash
javac RelativeErrorDemo.java
java RelativeErrorDemo
~~~

Exact output:

~~~text
largeLoose=true
largeTight=false
tiny=true
zeroVsTiny=false
signedZero=true
oppositeLarge=false
sameInfinity=true
notANumber=false
~~~

**Reading the output:**

- `1_000_000.0` and `1_000_000.5` differ by only about `5e-7` relatively, so they pass `1e-6` but fail `1e-7`.
- `1e-12` and `1.01e-12` differ by about 1%, so they pass a 2% threshold even though the absolute difference is only around `1e-14`.
- `0` and `1e-12` have a 100% relative discrepancy under the `max` denominator, so they are not considered close using pure relative tolerance below 1.
- `+0.0` and `-0.0` compare `==` as `true`, so they are accepted before computing the ratio.
- The policy here treats two infinities of **the same sign** as equal, infinities of opposite signs or compared with finite numbers as not close; `NaN` always returns `false`.

In practice, a system may require **rejecting all `NaN`/`Infinity`** instead of allowing same-sign infinities. If so, check `Double.isFinite(a) && Double.isFinite(b)` *before* `a == b` and return an error or `false` per the API contract. What matters is that the policy is **clearly documented and tested**.

## 5. Why Combine with Absolute Error Near 0?

A very common scenario: a mathematical algorithm expects `0.0`, but actual computation gives `1e-12`. Under symmetric relative error:

\[
\frac{|0 - 10^{-12}|}{\max(0, 10^{-12})} = 1
\]

A threshold of `relTol = 1e-6` rejects this difference, even though `1e-12` may fall well within measurement error or reasonable numerical limits of the problem.

The usual solution is to **combine an absolute condition or a relative condition**:

\[
\operatorname{near}(a,b) =
(|a-b| \le absTol)
\;\lor\;
\left(
\frac{|a-b|}{\max(|a|,|b|)} \le relTol
\right)
\]

where the `scale == 0` case and special values are handled separately.

It can also be written as `|a-b| <= max(absTol, relTol*scale)` on ordinary finite values, though **you should not multiply or subtract unchecked** when working near the limits of `double`. Checking the two branches separately avoids multiplying `relTol * scale` and lets you validate before computing the ratio.

The two parameters have **different roles**:

| Parameter | Unit | When used |
|---|---|---|
| `absTol` | Same unit as `a` and `b` | Allows small error near 0 |
| `relTol` | Dimensionless | Allows proportional error based on value magnitude |

For example, if the data is in meters, `absTol = 1e-9` means an absolute tolerance of 1 nanometer; `relTol = 1e-6` is a relative tolerance of one part per million. **Do not pick thresholds just because they look common**; choose them based on measurement accuracy and the cost of false acceptance.

## 6. Safe Hybrid Absolute/Relative Implementation for Finite Numbers

Create the file `HybridToleranceDemo.java`:

~~~java
public class HybridToleranceDemo {
    /**
     * Policy: accept if absolute error OR relative error is small enough.
     * Allows two infinities of the same sign to be equal; NaN is always unequal.
     */
    static boolean nearlyEqual(double a, double b,
                               double absTol, double relTol) {
        if (!Double.isFinite(absTol) || absTol < 0.0
                || !Double.isFinite(relTol)
                || relTol < 0.0 || relTol >= 1.0) {
            throw new IllegalArgumentException("invalid tolerance");
        }

        if (Double.isNaN(a) || Double.isNaN(b)) {
            return false;
        }
        if (a == b) {
            return true;
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }

        // Can become Infinity if a and b are extremely large with opposite signs.
        double diff = Math.abs(a - b);
        if (diff <= absTol) {
            return true;
        }

        // If both are finite with opposite signs or one is 0,
        // relative error >= 1. absTol was already checked above.
        if (a == 0.0 || b == 0.0 || ((a < 0.0) != (b < 0.0))) {
            return false;
        }

        double scale = Math.max(Math.abs(a), Math.abs(b));
        return diff / scale <= relTol;
    }

    public static void main(String[] args) {
        double absTol = 1e-10;
        double relTol = 1e-6;

        System.out.println("nearZero="
                + nearlyEqual(0.0, 1e-12, absTol, relTol));
        System.out.println("largeClose="
                + nearlyEqual(1_000_000.0, 1_000_000.5,
                        absTol, relTol));
        System.out.println("largeFar="
                + nearlyEqual(1_000_000.0, 1_000_002.0,
                        absTol, relTol));
        System.out.println("oppositeSmall="
                + nearlyEqual(1e-12, -1e-12, absTol, relTol));
        System.out.println("oppositeLarge="
                + nearlyEqual(Double.MAX_VALUE,
                        -Double.MAX_VALUE, absTol, relTol));
        System.out.println("exactZero="
                + nearlyEqual(0.0, -0.0, 0.0, 0.0));
        System.out.println("notFinite="
                + nearlyEqual(Double.NaN, 1.0, absTol, relTol));
    }
}
~~~

~~~bash
javac HybridToleranceDemo.java
java HybridToleranceDemo
~~~

Output:

~~~text
nearZero=true
largeClose=true
largeFar=false
oppositeSmall=true
oppositeLarge=false
exactZero=true
notFinite=false
~~~

**Explaining the sign condition:** When `a` and `b` are finite, non-zero, and have opposite signs, `|a-b| >= max(|a|,|b|)`. Thus the relative ratio is at least 1 and cannot satisfy `relTol < 1`. This case can only be accepted via **`absTol`** if both lie very close to 0. By checking `absTol` first, the function can still accept `1e-12` and `-1e-12` without equating two opposite-signed numbers at large scales.

**Why not compute `diff / scale` right from the start?** If `a == b == 0.0`, `scale` is 0 and `0.0 / 0.0` becomes `NaN`. If two very large values have opposite signs, `a-b` can become `Infinity`; the sign-check branch avoids relying on unnecessary ratios. For two finite numbers of the same sign, the difference magnitude cannot exceed the larger magnitude and subtraction cannot overflow to infinity.

## 7. Three Denominator Choices and When to Use Each

There is no single exclusive relative formula:

### 7.1. Based on a Reference Value

\[
\frac{|measured-reference|}{|reference|} \le relTol
\]

Suitable when there is a **non-zero reference** with physical or business meaning: a production target, a calibration standard, or a high-precision reference result. However, swapping `measured` and `reference` changes the denominator, which can change the conclusion.

For example, taking `reference = 100` and `measured = 101` yields a reference error of 1%; taking `reference = 101` and `measured = 100` yields an error of about 0.9901%.

### 7.2. Symmetric Based on the Largest Magnitude

\[
\frac{|a-b|}{\max(|a|,|b|)} \le relTol
\]

Suitable when there is no privileged reference, such as checking whether two independent calculation results are close to each other. This is the choice used in the two Java programs above.

### 7.3. Based on a Predefined Scale

A comparison can use an industry-standard `scale` denominator (device size, normalized domain, rated capacity) instead of picking from the two values. This approach is helpful **near 0** when the problem still has a natural scale.

**Important:** the choice of denominator must be grounded in the data's meaning. Do not call the three formulas completely equivalent, and do not state a `relTol` threshold without specifying the denominator.

## 8. `float` vs. `double` and the Meaning of Epsilon

`float` has about 24 bits of binary significand precision, and `double` has 53 bits. A measurement or algorithm in `float` typically incurs larger relative rounding error than the corresponding case in `double`, yet **there is no rule that whenever you use `double`, a threshold of `1e-12` is always suitable**.

Constants:

- `Math.ulp(1.0f)` is the distance to the next `float` above `1.0f`, approximately `1.1920929e-7`.
- `Math.ulp(1.0)` is the distance to the next `double` above `1.0`, approximately `2.220446049250313e-16`.

This is information about **representation resolution at a specific scale**, not a promise that every calculation has error within one ULP. Error can accumulate over many steps, originate from input data models, or result from an unstable algorithm.

### Commonly Misunderstood Names

- `Double.MIN_VALUE` is the smallest positive subnormal number greater than 0 for `double`, **not an epsilon for approximate comparison**.
- `Float.MIN_VALUE` is also the smallest positive subnormal number greater than 0, not a universal relative threshold.
- Java has no standard `Double.EPSILON` constant in `java.lang.Double` to automatically solve all approximate comparisons. `Math.ulp(1.0)` is often used to illustrate resolution near 1, but **the comparison threshold must still come from problem requirements**.

If you need to check **exact bit-level match**, or use numbers as identifier keys, never substitute a tolerance-based comparison for that requirement.

## 9. Common Traps: Overflow, Underflow, NaN, and Infinity

### 9.1. The Difference of Two Finite Numbers Can Overflow

~~~java
double a = Double.MAX_VALUE;
double b = -Double.MAX_VALUE;
double difference = Math.abs(a - b); // Infinity
~~~

This is an illustrative snippet. Both `a` and `b` are finite, but their mathematical difference exceeds the finite `double` range, so `difference` becomes `Infinity`. If you then naively compute `difference / Math.max(Math.abs(a), Math.abs(b))`, the ratio becomes `Infinity`, rather than the expected finite relative error of around 2. Even though the two numbers should not be deemed "close," this simple division shows how **a naive formula can lose information at the boundary**.

With `relTol < 1`, simply rejecting opposite-sign cases (after the absolute check in the hybrid version) avoids computing ratios in the difference-overflow region. If a problem demands **accurately computing ratios for thresholds greater than or equal to 1**, you need a different algorithm that scales values rather than reusing a function designed for `relTol < 1`.

### 9.2. Below Representation Limits and Tiny `scale`

Near 0, `double` values can fall into the **subnormal** range, and arithmetic can underflow. Relative error can then become very sensitive to a one-ULP change; a comparison with a meaningful `absTol` is usually more helpful.

However, an `absTol` that is too large for the business meaning also causes **false positives**: two numbers that differ significantly in proportion are treated as close simply because both are small. Therefore, never pick `absTol` mechanically as "some small number."

### 9.3. `NaN` and `Infinity` Are Not Ordinary Finite Numbers

In Java:

- `Double.NaN == Double.NaN` is `false`.
- `Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY` is `true`.
- `Double.isNaN(a)` or `Double.isFinite(a)` provides explicit checks.
- If only one operand is infinite and the other is finite, closeness as defined in both examples is `false`.

**Policy of the two examples:** NaN is never nearly equal; infinity is only nearly equal to itself with the same sign. An input-validation library may choose to **reject all non-finite values** upfront so conclusions are meaningful for measurements. There is no single exception policy for every application.

### 9.4. `-0.0` and `+0.0`

`-0.0 == 0.0` evaluates to `true` even though bit representation and signs when dividing by 0 can differ. Both sample functions accept them as equal, matching `==` semantics. If an application needs to distinguish the sign bit of zero, use a suitable separate check rather than approximate equality.

## 10. Example Testing Failures from Choosing a Fixed Absolute Threshold

A common mistake is using only the condition:

~~~java
Math.abs(a - b) < 1e-6
~~~

Test it at two different scales:

- `a = 1e-12`, `b = 2e-12`: the difference is only `1e-12`, so `1e-6` accepts them, even though they differ by **50% under the max denominator**.
- `a = 1_000_000`, `b = 1_000_000.5`: the difference is `0.5`, so `1e-6` rejects them, even though they differ by **about 0.00005%**.

Create the file `AbsoluteVsRelativeDemo.java`:

~~~java
public class AbsoluteVsRelativeDemo {
    static boolean absoluteClose(double a, double b, double absTol) {
        return Math.abs(a - b) <= absTol;
    }

    static boolean relativeClose(double a, double b, double relTol) {
        if (a == b) {
            return true;
        }
        double scale = Math.max(Math.abs(a), Math.abs(b));
        return Math.abs(a - b) / scale <= relTol;
    }

    public static void main(String[] args) {
        System.out.println("tinyAbs="
                + absoluteClose(1e-12, 2e-12, 1e-6));
        System.out.println("tinyRel="
                + relativeClose(1e-12, 2e-12, 1e-6));
        System.out.println("largeAbs="
                + absoluteClose(1_000_000, 1_000_000.5, 1e-6));
        System.out.println("largeRel="
                + relativeClose(1_000_000, 1_000_000.5, 1e-6));
    }
}
~~~

~~~bash
javac AbsoluteVsRelativeDemo.java
java AbsoluteVsRelativeDemo
~~~

Output:

~~~text
tinyAbs=true
tinyRel=false
largeAbs=false
largeRel=true
~~~

**Limitation of this secondary example:** `relativeClose` in this class **is only meant to illustrate comparing the two non-zero same-sign finite pairs called from `main`**. It is not a safe library function for arbitrary inputs, as it lacks handling for `NaN`/infinity, `scale == 0`, and difference overflow. In application code, use the full validation implementations in Section 4 or Section 6, or apply a tested domain-specific policy.

## 11. Approximate Equality Is Not an Equivalence Relation

An easily overlooked point is that "nearly equal" with positive tolerance is **usually not transitive**:

- `near(a, b) == true` can hold.
- `near(b, c) == true` can hold.
- Yet `near(a, c) == false`.

For example, using an absolute threshold of `0.1`: `a=0.0`, `b=0.09`, `c=0.18`. Adjacent pairs differ by 0.09, while `a` and `c` are 0.18 apart. With relative tolerance, non-transitivity also occurs among nearby positive values.

**Design consequence:** Do not use `nearlyEqual` as if it were `Object.equals`, or directly alter `equals`/`hashCode` of `HashMap`/`HashSet` keys. Collection structures generally require a stable equivalence relation; using approximate equality can produce unexpected behavior in grouping, lookup, and sorting.

If you need to cluster nearby values, define a clustering algorithm or **quantization** with explicit boundary rules rather than assuming approximate equality is transitive. If you need to compare identifiers or exact results, use the appropriate numeric type and exactness policy.

## 12. Not Every Problem Should Use Relative Tolerance

| Problem | Approach worth considering |
|---|---|
| Comparing two numerical/measurement results with a wide scale range | Symmetric relative error, or combined with absolute |
| Comparing against a non-zero **standard value** | Relative error against `reference` |
| Comparing numbers near 0 with measurement error in clear units | Absolute threshold in physical units |
| Checking exact equality of integer quantities | `==` on `int`/`long` or exact integer types |
| Comparing exact decimal monetary data | `BigDecimal` and scale/rounding policy, not arbitrary `double` tolerance |
| Comparing bit representations of floating-point numbers | Appropriate bit inspection, not approximate equality |
| Defining a sort order | Comparator with consistent ordering; avoid non-transitive "approximate equality" |

Default tolerances like "always `1e-6`" or "always `Double.MIN_VALUE`" are a sign to re-examine actual precision requirements.

## 13. Common Misconceptions

1. **"Relative error is `Math.abs(a-b)`."** No: that is **absolute** error. Relative error must be measured against a defined scale.
2. **"`Math.abs(a-b) / Math.abs(b)` is always safe."** No: `b` can be 0, near 0, or `a-b` can overflow; furthermore, a denominator based on `b` is asymmetric.
3. **"Two numbers near 0 will definitely pass a small relative threshold."** No: `0` vs. `1e-12` has a symmetric relative error of 1.
4. **"A `1e-12` threshold is right for every `double`."** No: it must be chosen based on data scale, operations, step count, and business goals.
5. **"`Double.MIN_VALUE` is `double`'s epsilon."** No: it is the smallest positive subnormal number, not a general relative error threshold.
6. **"If the operands are finite, `a-b` is always finite."** No: two large numbers of opposite signs can make the difference overflow to infinity.
7. **"`NaN` can be handled like finite numbers."** No: it requires an explicit policy; `NaN == NaN` is `false`.
8. **"Two very close numbers can serve as equal keys in any `HashMap`."** No: closeness with a positive threshold is not necessarily transitive.
9. **"Just pick an error percentage; you do not need to pick a denominator."** No: the denominator is part of the problem definition; `reference`, `max`, and a fixed standard scale can yield different results.
10. **"Increasing `relTol` up to 100% causes no problems."** An overly wide threshold destroys the meaning of "close"; the sample functions intentionally restrict `relTol < 1` and require a different policy if a wider range is needed.

## 14. Checklist for Building an Approximate Comparison

1. **Identify the data:** measurement quantity, simulation result, price, ratio, or identifier?
2. **Choose the error definition:** against a reference value, against `max(|a|, |b|)`, or a meaningful fixed scale.
3. **Set `relTol` from requirements**, not from an unexplained default constant.
4. **Handle near 0:** if needed, set `absTol` according to data units and resolution.
5. **Check special inputs:** `NaN`, infinity, signed zero; decide whether they are rejected or compared by a specific rule.
6. **Avoid intermediate overflow** when numbers are finite yet huge with opposite signs.
7. **Do not confuse "nearly equal" with "exactly equal."** Especially for keys, grouping, sorting, and data validation.
8. **Write boundary tests:** identical numbers, adjacent numbers, above/below threshold, near 0, opposite signs, max values, infinity, NaN, negative/NaN thresholds.
9. **Document whether the API returns `boolean` or throws an exception** for invalid thresholds; the sample throws `IllegalArgumentException`.
10. **Assess source error:** if a sensor is accurate to 1%, a `1e-12` threshold does not reflect real data certainty even when using `double`.

## 15. Self-Check

1. How does absolute error differ from relative error? What are the units of each?
2. Why do `a=1e-12` and `b=2e-12` have a tiny absolute error yet a large symmetric relative error?
3. Does relative error against `reference` stay the same when swapping the two numbers?
4. Why are `0.0` and `1e-12` not close under pure `relTol=1e-6`, yet can be close under `absTol=1e-10`?
5. Why should `a == b` be handled before dividing by `max(|a|,|b|)`?
6. If one number is `Double.NaN`, should you use `==` or division directly to conclude closeness?
7. What is the `double` difference `a-b` for the two finite numbers `Double.MAX_VALUE` and `-Double.MAX_VALUE`?
8. When should you choose `BigDecimal` instead of comparing `double` with tolerance?
9. Why is approximate equality unsuitable as a replacement for `equals`/`hashCode`?
10. If two measurements share the same unit but range from `1e-9` to `1e9`, why is a standalone absolute threshold usually insufficient?

**Answer hints:** (1) Absolute is discrepancy in the same units; relative is a dimensionless ratio. (2) The difference is half the larger value, so the ratio is `0.5`. (3) No, because changing the reference value changes the denominator. (4) Relative error equals 1, while absolute difference is `1e-12`. (5) Avoids `0/0` when both are 0 and handles exact matches cleanly. (6) Handle `NaN` by policy; in the examples it is `false`. (7) Overflows to `Infinity`. (8) When business decimal exactness is required, such as money. (9) Approximate equality may lack transitivity. (10) Meaningful error depends on scale, usually requiring a relative part combined with an absolute condition near 0.

**Remember:** **Relative error evaluates discrepancy relative to value scale**, enabling comparisons of `float`/`double` numbers across many magnitudes. Clearly choose the **denominator**, set **thresholds from problem requirements**, and handle **near 0, NaN, infinity, and intermediate overflow**. When needed, combine **absolute or relative error**, rather than using one fixed epsilon for every situation.
