# Limitations of a Fixed Epsilon Constant Across All Problems

When working with floating-point numbers `float` and `double`, exact equality comparison using `==` can fail even when two results are expected to be mathematically equal. A common approach is to compare the absolute difference against a small threshold, often called **epsilon**:

~~~java
boolean approximatelyEqual = Math.abs(a - b) <= 1e-9;
~~~

However, **there is no single fixed epsilon value suitable for every problem, every scale, and every number magnitude**. A value of `1e-9` can be far too loose for numbers around `1e-12`, yet far too strict for numbers around `1e12`. What counts as "small" must be defined according to units, acceptable error levels, data magnitudes, and the purpose of the comparison.

This lesson distinguishes absolute error, relative error, and ULP units; demonstrates the limitations of using a single absolute epsilon; and then constructs purposeful comparisons in Java 17+, including handling special values such as NaN and infinity.

## 1. Why Do Floating-Point Numbers Have Error?

`float` and `double` are represented by Java as finite binary floating-point numbers according to IEEE 754. Many familiar decimal fractions, such as `0.1` and `0.2`, have no exact finite binary representation. Storage and calculation require rounding.

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum == 0.3);        // false
System.out.println(sum);               // 0.30000000000000004
~~~

The snippet above is illustrative and meant to be placed inside a Java method. The result `sum` differs at the bit level from the literal `0.3` by a small amount, even though in ideal decimal arithmetic `0.1 + 0.2 = 0.3`.

Not every floating-point calculation produces a discrepancy: numbers with exact binary representations such as `0.5`, `0.25`, or small integers can yield exact results in certain operations. Error depends on both the data and the operations, rather than a blanket property that "no `double` numbers can ever be compared for equality."

Nor should **representation error** be conflated with **measurement error**. A value `3.14159` rounded from an experimental measurement can carry uncertainty far greater than `double` rounding error. Application comparison thresholds may need to reflect measurement error, sensor limits, unit conversions, or business criteria alongside machine error.

## 2. Three Concepts Often Lumped Together as Epsilon

The word "epsilon" causes confusion because it is used in multiple contexts:

| Concept | Meaning | Example or how it is determined |
| --- | --- | --- |
| **Absolute tolerance** | Maximum acceptable absolute difference, in **the unit of the data** | `absTol = 0.01` meters |
| **Relative tolerance** | Acceptable difference relative to **value magnitude**; dimensionless | `relTol = 1e-6` |
| **Machine epsilon** | Characteristic representation spacing of a floating-point format around 1.0; not a default business tolerance | For `double`, `Math.ulp(1.0)` spacing is `2.220446049250313E-16` |

Machine epsilon around 1.0 **does not fix the spacing between every pair of representable numbers**. The spacing between adjacent floating-point numbers changes with magnitude and exponent region. Java provides `Math.ulp(x)` to inspect the unit in the last place at `x` (ULP, *unit in the last place*).

Example:

~~~java
System.out.println(Math.ulp(1.0));   // 2.220446049250313E-16
System.out.println(Math.ulp(1e12));  // 1.220703125E-4
~~~

ULP around `1e12` is vastly larger than ULP around `1.0`. Therefore, using a tiny absolute threshold such as `1e-15` or `1e-9` without considering data magnitude can be unreasonable. Neither ULP nor machine epsilon **decides on its own** what discrepancy is acceptable in a specific problem.

## 3. First Limitation: A Fixed Epsilon Is Too Loose for Very Small Numbers

Suppose we use a single shared absolute tolerance:

~~~java
static boolean fixed(double a, double b) {
    return Math.abs(a - b) <= 1e-9;
}
~~~

This is an illustrative method to be placed inside a Java class. Consider:

~~~java
double a = 1e-12;
double b = 2e-12;
boolean equal = Math.abs(a - b) <= 1e-9; // true
~~~

The absolute difference is `1e-12`, which is smaller than epsilon `1e-9`. Yet `b` is **double** `a`: the relative difference against the larger magnitude is 50% when using `max(|a|, |b|)` as the denominator. In a problem requiring relative accuracy, treating these two numbers as "nearly equal" makes no sense.

Conclusion: **an absolute epsilon can hide significant discrepancies at small value scales**. You cannot judge strictness merely by looking at the exponent of epsilon.

## 4. Second Limitation: A Fixed Epsilon Is Too Strict for Large Numbers

Consider two results that are very close relative to their scale:

~~~java
double a = 1e12;
double b = 1e12 + 0.01;

boolean equal = Math.abs(a - b) <= 1e-9; // false
~~~

The absolute difference is roughly `0.01`, many times larger than the constant `1e-9`, so the result is `false`. However, relative to a magnitude of `1e12`, this difference has a ratio of about `1e-14`. In many problems with a relative tolerance of `1e-12`, two such values would be acceptable.

Because `double` rounds to a binary number grid, the actual difference computed from the two stored values may not be `0.01` exactly; in this example it is approximately `0.010009765625`. That further demonstrates why you must reason over **the actually represented values**, instead of assuming every decimal literal is stored accurately.

Conclusion: **a very small absolute epsilon can reject negligible proportional differences at large value scales**.

## 5. Evaluating Absolute and Relative Error

Absolute difference between `a` and `b`:

\[
d_{\mathrm{abs}} = |a-b|
\]

A symmetric form of relative difference, when at least one value is nonzero, is:

\[
d_{\mathrm{rel}} =
\frac{|a-b|}{\max(|a|, |b|)}
\]

Where:

- Absolute difference retains the data unit: a `0.01` second difference differs from `0.01` currency units or `0.01` meters.
- Relative difference is dimensionless. It is useful when the scale spans many orders of magnitude.
- When both numbers are 0, the ratio expression above has a zero denominator; if one or both numbers are near 0, relative difference becomes overly sensitive and fails to capture "near 0" well.

For data near 0, an **absolute threshold based on problem semantics** is needed. For large data, a relative threshold usually reflects the desired accuracy better. Hence, a common combined rule uses two distinct tolerances:

\[
|a-b| \le \max\left(\mathrm{absTol},
\mathrm{relTol}\cdot\max(|a|,|b|)\right)
\]

This can be written logically as:

~~~java
difference <= absTol || difference <= relTol * scale
~~~

Where `difference = Math.abs(a - b)` and `scale = Math.max(Math.abs(a), Math.abs(b))`. This is a **design pattern**, not a theorem claiming every application domain must choose the same normalization or the same tolerances.

### Comparison Examples

| Two values | absTol | relTol | Meaning |
| --- | ---: | ---: | --- |
| `0.0` and `1e-13` | `1e-12` | `1e-9` | Can accept tiny differences near 0 |
| `1e-12` and `2e-12` | `1e-15` | `1e-9` | Should not treat as equal just because absolute numbers are tiny |
| `1e12` and `1e12 + 0.01` | `1e-15` | `1e-12` | Can accept a larger absolute difference that is relatively small |

The thresholds in the table are meant to **illustrate selection by requirement**; there are no default values recommended by Java or IEEE 754 for all programs.

## 6. Choosing Tolerances Based on the Problem Domain

Before writing a comparison function, determine:

1. **Units and resolution:** temperature data accurate to 0.1°C differs from position data needing 0.1 micrometer accuracy. `absTol` carries the unit corresponding to the compared quantity.
2. **Scale and orders of magnitude:** measured values varying from `1e-12` to `1e12` generally require considering relative error or appropriate normalization.
3. **Error sources:** binary representation, adding/subtracting nearby values, measurement, data conversion, and how the algorithm accumulates error.
4. **Consequences of discrepancy:** display acceptance criteria, algorithm testing, safety alerts, and convergence conditions may demand different levels of strictness.
5. **Confidence level:** thresholds should come from specifications, instrument resolution, analytical error bounds, benchmarked empirical testing, or acceptance constraints; do not pick `1e-9` simply because it looks small.

For example, when checking a sensor with a resolution of 0.01 units, comparing results with an epsilon of `1e-15` does not reflect actual measurement capability. In solving systems of equations with solutions near 0, checking only with relative error can cause confusing behavior. Conversely, for quantities always within a narrow scale, a fixed, specified absolute tolerance can be **very appropriate**.

You do not have to force every comparison to use both absTol and relTol. These two criteria are merely tools. Choose them based on semantics rather than a "magic formula."

## 7. Java 17+ Example: Fixed vs. Combined Comparison

Create the file `EpsilonLimitsDemo.java`:

~~~java
public class EpsilonLimitsDemo {
    static boolean fixed(double a, double b, double epsilon) {
        if (!Double.isFinite(epsilon) || epsilon < 0.0) {
            throw new IllegalArgumentException("epsilon");
        }
        return Double.isFinite(a) && Double.isFinite(b)
                && Math.abs(a - b) <= epsilon;
    }

    static boolean mixed(double a, double b, double absTol, double relTol) {
        if (!Double.isFinite(absTol) || !Double.isFinite(relTol)
                || absTol < 0.0 || relTol < 0.0 || relTol >= 1.0) {
            throw new IllegalArgumentException("tolerance");
        }
        if (a == b) return true; // Both are the same infinity, or +0.0/-0.0
        if (!Double.isFinite(a) || !Double.isFinite(b)) return false;

        double difference = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        return difference <= absTol || difference <= relTol * scale;
    }

    public static void main(String[] args) {
        double sum = 0.1 + 0.2;
        System.out.println("sum == 0.3: " + (sum == 0.3));
        System.out.println("fixed sum: " + fixed(sum, 0.3, 1e-9));

        System.out.println("small fixed: "
                + fixed(1e-12, 2e-12, 1e-9));
        System.out.println("small mixed: "
                + mixed(1e-12, 2e-12, 1e-15, 1e-9));

        System.out.println("large fixed: "
                + fixed(1e12, 1e12 + 0.01, 1e-9));
        System.out.println("large mixed: "
                + mixed(1e12, 1e12 + 0.01, 1e-15, 1e-12));

        System.out.println("near zero mixed: "
                + mixed(0.0, 1e-13, 1e-12, 1e-9));
        System.out.println("NaN mixed: "
                + mixed(Double.NaN, 1.0, 1e-12, 1e-9));
        System.out.println("same infinity mixed: "
                + mixed(Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, 1e-12, 1e-9));

        System.out.println("ulp(1): " + Math.ulp(1.0));
        System.out.println("ulp(1e12): " + Math.ulp(1e12));

        System.out.println("not transitive: "
                + (fixed(0.0, 0.75, 1.0)
                && fixed(0.75, 1.5, 1.0)
                && !fixed(0.0, 1.5, 1.0)));
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac EpsilonLimitsDemo.java
java EpsilonLimitsDemo
~~~

Verified output:

~~~text
sum == 0.3: false
fixed sum: true
small fixed: true
small mixed: false
large fixed: false
large mixed: true
near zero mixed: true
NaN mixed: false
same infinity mixed: true
ulp(1): 2.220446049250313E-16
ulp(1e12): 1.220703125E-4
not transitive: true
~~~

### Output Analysis

- `fixed sum` is `true` because `0.1 + 0.2` and `0.3` differ by only about `5.55e-17`, smaller than `1e-9`.
- `small fixed` is `true` while `small mixed` is `false`: absolute epsilon `1e-9` is too wide for the pair `1e-12` and `2e-12`; a stricter relative criterion reflects the large proportional discrepancy.
- `large fixed` is `false` while `large mixed` is `true`: the `0.01` difference is too large for an absolute epsilon of `1e-9`, yet sufficiently small at a `1e-12` ratio on a `1e12` scale.
- `near zero mixed` is `true` thanks to `absTol`: a purely relative rule is not designed to handle the region near 0 in the same meaningful way.
- `Math.ulp` illustrates that representation spacing changes sharply with magnitude.
- `not transitive` being `true` proves that **tolerance-based near equality is not transitive**: `0` is close to `0.75`, `0.75` is close to `1.5`, yet `0` is not close to `1.5` under the same epsilon of 1.

The `mixed` example illustrates one specific comparison policy. It deliberately treats two **identical infinities** as equal, while NaN is never equal. In an application requiring both operands to be finite, move the `Double.isFinite(a) && Double.isFinite(b)` check **before** the `a == b` branch. No single infinity-handling rule fits every business domain.

For arguments of very large magnitude and opposite signs, `a - b` can overflow to infinity even though both `a` and `b` are finite. In the example, `difference` is then infinite and fails the finite thresholds; the method returns `false`. When building specialized error-analysis algorithms, consider both overflow and underflow when computing differences, rather than assuming subtraction is always exact.

## 8. Why Is "Approximate Equality" Not True Equality?

Consider `epsilon = 1.0`:

- `a = 0.0` is close to `b = 0.75` because the difference is 0.75.
- `b = 0.75` is close to `c = 1.5` because the difference is 0.75.
- `a = 0.0` is **not** close to `c = 1.5` because the difference is 1.5.

Because it lacks transitivity, checking `Math.abs(a - b) <= epsilon` does not form a mathematical equivalence relation. Consequences:

- Do not use "equal within epsilon" directly as the definition of `equals`/`hashCode` on objects if it violates the equivalence contract.
- Do not arbitrarily use a comparator that "returns 0 if nearly equal" in `TreeSet`, `TreeMap`, or `Collections.sort`: it can violate the ordering contract of `Comparator` and cause unpredictable behavior.
- If you need to group numbers into buckets, define a consistent **quantization rule**, unit, boundary, and negative-number handling. Buckets still have boundary discrepancies, but they produce deterministic keys instead of arbitrary pairwise comparisons.

In some business domains, approximate comparison is appropriate for **verifying results**, whereas exact comparison is used for **identity or data keys**. These two concepts must be kept separate.

## 9. Special Cases to Handle

### 9.1. NaN

For `double a = Double.NaN`, every `a == a` is `false`, and `<`, `<=`, `>`, `>=` involving NaN are also `false`. Do not assume a near-equality expression treats NaN as a "value to ignore"; decide explicitly:

~~~java
if (Double.isNaN(a) || Double.isNaN(b)) {
    // Reject, report missing data, or apply a custom policy.
}
~~~

This is an illustrative check. For wrapper objects, `Double.equals` has its own contract regarding NaN, different from the primitive `==` operator.

### 9.2. Infinity

`Math.abs(Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY)` is NaN, so even two infinities of the same sign are not considered nearly equal by a simple difference expression.

If the application accepts two identical infinities, check `a == b` **before** computing `Math.abs(a-b)`. If the application only accepts finite numbers, check `Double.isFinite` first.

### 9.3. Two Forms of Zero

`+0.0 == -0.0` is `true` for primitives, yet the two bit patterns have different signs. The `mixed` function treats these two zeros as equal by arithmetic convention. If the sign bit matters (for example, in certain IEEE 754 computational contexts), define a separate criterion or inspect `Double.doubleToRawLongBits`/`Double.doubleToLongBits` as needed.

### 9.4. Smallest Value and Underflow

`Double.MIN_VALUE` is the smallest nonzero positive `double` (subnormal), **not the most negative value** of `double`. Very close to 0, `relTol * scale` can fall below the representable range and become 0, so an appropriate absolute tolerance often plays a critical role.

### 9.5. Division to Compute Relative Error

The expression `Math.abs(a-b) / Math.max(Math.abs(a), Math.abs(b))` can hit a zero denominator when both are 0, or encounter special floating-point cases. Comparing via multiplication such as `difference <= relTol * scale` avoids direct division, yet still requires watching for overflow/underflow and validating the value domain. Not every algebraically equivalent implementation is strictly equivalent when executed with finite floating-point numbers.

## 10. Distinguishing Rounding Error from Algorithm Stability

An algorithm can produce large errors due to **loss of significant digits** (catastrophic cancellation), iterative error accumulation, or poor problem conditioning, not merely from picking the wrong epsilon. For example, when taking the difference of two nearby numbers, shared significant digits can cancel out; the relative accuracy of the difference can be very poor.

Therefore, if two computation methods on the same data are not close, do not immediately **increase epsilon until the tests pass**. Doing so can mask algorithmic bugs, unit conversion errors, invalid input conditions, or the choice of an unstable numerical method.

A sound workflow:

1. Use verified quantities/units, estimate the value scale, and determine the acceptable error interval.
2. Check whether the computation method is well-conditioned; when needed, use more stable operations or higher-precision algorithms.
3. Choose test criteria based on actual requirements and error analysis, then lock them in tests; do not tweak them just to hide failing tests.
4. Test near 0, very large/small values, NaN, infinity, and negative numbers if they belong to the input domain.
5. Document the rationale and scope of `absTol` and `relTol` in documentation or constant names instead of a vague global variable like `EPSILON`.

A financial problem requiring exact decimal values should likely use `BigDecimal`, smallest-unit integer arithmetic (such as whole cents), or a specified arithmetic model; changing epsilon does not turn `double` into an exact decimal number. In computational geometry, near-collinear orientation tests may require robust predicates instead of arbitrary epsilon comparisons. Those are **problem design** choices; there is no single universal constant.

## 11. Common Pitfalls

**Pitfall 1 — Treating `1e-9` as "the precision of double."**  
`double` has magnitude-dependent resolution. `1e-9` is an application-chosen tolerance, not a fixed property of `double`.

**Pitfall 2 — Using only relative error near 0.**  
When the scale is near 0, the relative threshold can be extremely small or 0; consider an `absTol` meaningful to the problem domain.

**Pitfall 3 — Using absolute epsilon while ignoring units.**  
A difference of 0.01 meters and 0.01 seconds cannot arbitrarily share the same tolerance unless the design specification explicitly states so.

**Pitfall 4 — Failing to handle NaN and infinity.**  
`NaN` has special comparison behavior; subtracting infinity from itself produces NaN. Choose a policy for each case.

**Pitfall 5 — Building an "approximately equal" Comparator.**  
Approximate equality can be non-transitive, so do not use it directly for equivalence or ordering in data structures.

**Pitfall 6 — Increasing epsilon when a test fails.**  
Adjusting tolerances must be justified by computation error, input data, or acceptance constraints; arbitrarily large thresholds can hide real bugs.

## 12. Self-Check Questions

**Question 1.** Why can `Math.abs(a-b) <= 1e-9` return `true` for `a=1e-12`, `b=2e-12` even though they differ greatly in proportion?  
**Answer:** The absolute difference `1e-12` is smaller than `1e-9`, yet `b` is double `a`; the absolute epsilon is far too large relative to the value scale.

**Question 2.** Why is a very small absolute epsilon inappropriate for `a=1e12`, `b=1e12+0.01`?  
**Answer:** The absolute difference is roughly 0.01, yet the relative difference is only about `1e-14`. If the problem accepts that relative level, using only an absolute epsilon of `1e-9` is overly strict.

**Question 3.** Are machine epsilon and absTol the same?  
**Answer:** No. Machine epsilon describes representation spacing related to the floating-point format around 1; absTol is the **problem's** acceptance criterion for absolute difference.

**Question 4.** Why can `Double.isFinite(a) && Double.isFinite(b)` be necessary before approximate comparison?  
**Answer:** NaN and infinity are not finite values. If the business domain only allows finite numbers, they must be rejected by policy rather than relying on incidental outcomes of subtraction or relational operators.

**Question 5.** With `epsilon=1.0`, why can't `equals` be built from the relation `|a-b|<=epsilon`?  
**Answer:** We can have `a~b` and `b~c` yet `a!~c`, meaning the relation is not transitive, violating the equivalence contract of `equals`.

**Question 6.** When should you use `BigDecimal` instead of increasing epsilon?  
**Answer:** When exact decimal values, deterministic rounding rules, or monetary representation per specification are required; epsilon only defines "near equality," it does not recover lost decimal digits.

## 13. Key Takeaways

- Epsilon used for approximate comparison is a **context-dependent tolerance**; there is no single optimal fixed value for all programs.
- **Absolute error** has units and fits fixed difference bounds; **relative error** scales with magnitude and is useful when data spans many scales.
- Combining absTol and relTol often helps handle both near-0 regions and very large numbers, but thresholds must be defined from concrete requirements.
- ULP and machine epsilon describe floating-point representation, not business tolerances.
- Consider NaN, infinity, underflow/overflow, non-transitivity, and algorithmic stability before turning an approximate comparison into a critical rule.
