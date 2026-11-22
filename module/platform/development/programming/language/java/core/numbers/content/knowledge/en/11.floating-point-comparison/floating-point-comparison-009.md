# Combining Absolute and Relative Error When Comparing Floating-Point Numbers in Java

## 1. Why Does Floating-Point Comparison Need an Error Threshold?

`float` and `double` in Java use binary floating-point representation. Many decimal values, such as `0.1`, have no exact finite binary representation. During calculations, operations can round, producing a result close to the expected value without sharing the exact same bit pattern.

Example:

```java
double computed = 0.1 + 0.2;
double expected = 0.3;

System.out.println(computed == expected); // false
System.out.println(computed);              // 0.30000000000000004
System.out.println(expected);              // 0.3
```

`==` answers the question: *are the two current `double` operands equal under Java's operator rules?* It does not answer the question: *are the two values close enough within the problem's tolerance?*

When a problem allows error, we usually compare:

\[
|a-b|\le T,
\]

where `T` is the tolerance threshold. The challenge is **which threshold fits the magnitude of the data**. A fixed threshold can be reasonable near 0 yet overly strict for large numbers; conversely, a magnitude-proportional threshold can approach 0 and fail to protect small results.

Therefore, in many approximate computation problems, we combine **absolute error** and **relative error**. This is an application-chosen criterion for accepting discrepancy, not a rule that "makes every `double` comparison right."

## 2. How Do Absolute and Relative Error Differ?

### 2.1. Absolute Error

Given a computed value `a` and a reference value `b`:

\[
E_{\text{abs}}=|a-b|.
\]

For example, `a = 10.002` and `b = 10.000` have an absolute error of roughly `0.002`. If the data is in meters, the absolute tolerance is also interpreted in meters; if in seconds, in seconds.

Comparison condition using only absolute error:

\[
|a-b|\le \text{absTol}.
\]

In Java:

```java
boolean closeByAbsoluteTolerance =
        Math.abs(a - b) <= absTol;
```

The snippet above is an **expression illustration**, assuming `a`, `b`, and `absTol` are already declared and finite with `absTol >= 0`. For arbitrary inputs, you must separately handle `NaN`, infinity, and subtraction overflowing to infinity.

Absolute error fits when there is a practically meaningful maximum discrepancy interval. For instance, if a length sensor permits a deviation of `0.001` meters, an absolute threshold of `0.001` makes sense even when measurements are near 0.

Drawback: a threshold like `1e-9` can be too large when comparing values around `1e-12`, yet too small when comparing results on the order of billions.

### 2.2. Relative Error

When there is a reference value `b != 0`, a common form is:

\[
E_{\text{rel,ref}}=\frac{|a-b|}{|b|}.
\]

If `b = 1_000_000` and `a = 1_000_000.001`, the absolute difference is around `0.001`, while the relative difference is about `10^{-9}` (one part per billion).

This is a good interpretation when **`b` is a meaningful standard value**, such as an independent reference result or calibration standard. However, the `|b|` denominator causes trouble when `b = 0` and makes the criterion overly strict when `b` is tiny.

When comparing **two peer results** (where neither is the designated standard), symmetric normalization is commonly used:

\[
S=\max(|a|,|b|),\qquad
|a-b|\le \text{relTol}\times S.
\]

This approach favors neither side and gives the same result when `a` and `b` are swapped. `relTol` is dimensionless; for instance, `1e-9` corresponds to a tolerance of about one part per billion **relative to the magnitude scale `S`**. If both equal 0, handle that separately or combine with an absolute threshold.

**Distinguish clearly:** "Relative error" has multiple ways to define the denominator depending on the problem. Using `max(|a|, |b|)` is one symmetric choice for approximate equality comparison, not the only valid denominator across all domains.

## 3. Combining Both Thresholds into One Comparison

A widely used criterion:

\[
\boxed{|a-b|\le\max\bigl(\text{absTol},
\text{relTol}\cdot\max(|a|,|b|)\bigr)}
\]

where:

- `absTol >= 0`: absolute tolerance, in the same units as `a` and `b`;
- `relTol >= 0`: relative tolerance, dimensionless;
- `max(|a|, |b|)`: symmetric magnitude scale;
- the `<=` sign specifies that a discrepancy equal to the threshold is also accepted.

The condition above is equivalent to:

\[
|a-b|\le\text{absTol}
\quad\text{OR}\quad
|a-b|\le\text{relTol}\times\max(|a|,|b|).
\]

That means two values are considered "close enough" if they satisfy **at least one** criterion. When one value is near 0, the absolute threshold protects the comparison. When both have significant magnitude, the relative threshold is usually the deciding factor.

Another rule that is also valid depending on the literature/application is:

\[
|a-b|\le \text{absTol}
+\text{relTol}\cdot\max(|a|,|b|).
\]

The **additive** form is looser than or equal to the **max** form because the sum of two non-negative numbers is at least as large as the greater one. Do not treat the two forms as equivalent or mix them when consistency with a specific standard, library, or test suite is required. This lesson uses the **max form** throughout for clarity in explanation and testing.

### Illustration at Three Scales

Assume `absTol = 1e-9`, `relTol = 1e-9`:

| Value pair | Approximate absolute difference | Governing threshold | Close enough? |
| --- | ---: | --- | --- |
| `0.0` and `1e-10` | `1e-10` | `absTol = 1e-9` | Yes |
| `0.0` and `1e-7` | `1e-7` | `absTol = 1e-9` | No |
| `1e6` and `1e6 + 1e-4` | `1e-4` | `relTol × 1e6 ≈ 1e-3` | Yes |
| `1e6` and `1e6 + 1e-2` | `1e-2` | `relTol × 1e6 ≈ 1e-3` | No |
| `100.0` and `101.0` | `1.0` | `relTol × 101 ≈ 1.01e-7` | No |

Conclusions depend on the **chosen pair of thresholds**. There is no default `absTol`/`relTol` pair suitable for every scale, calculation, and accuracy requirement.

### Why Not Apply a Relative Threshold Alone Near 0?

With `a = 0.0` and `b = 1e-12`, we have `S = 1e-12`. If `relTol = 1e-9`, the relative threshold is only `1e-21`, so the comparison reports them as different even though a difference of `1e-12` may be smaller than valid measurement error. The absolute threshold provides a practical margin of acceptance around 0.

Conversely, if the data genuinely needs to distinguish `0` from `1e-12` (such as pico-scale signals), setting `absTol = 1e-9` would be far too lenient. **Units and business requirements must determine `absTol`**, not a habit of using `1e-9` in every program.

## 4. The `approximatelyEqual` Function for `double` in Java 17

A usable function must also make explicit how special values are handled. In this lesson, we choose the policy:

- `NaN` is not "nearly equal" to any value, including `NaN`.
- Two infinities of **the same sign** are considered equal because they are equal under `==`; infinities of opposite signs or compared with finite numbers are not considered close.
- `+0.0` and `-0.0` are considered numerically equal.
- Tolerances must be finite and non-negative; to avoid overly permissive relative tolerances, require `relTol < 1.0`.
- For two finite values that are not exactly equal, apply the combined `max`-form formula.

Save to `ApproximatelyEqual.java`:

```java
public final class ApproximatelyEqual {
    private ApproximatelyEqual() {
    }

    public static boolean isClose(
            double a, double b, double absTol, double relTol) {

        if (!Double.isFinite(absTol) || absTol < 0.0
                || !Double.isFinite(relTol)
                || relTol < 0.0 || relTol >= 1.0) {
            throw new IllegalArgumentException("Invalid tolerances");
        }

        // By the example's policy, NaN is not compared for closeness.
        if (Double.isNaN(a) || Double.isNaN(b)) {
            return false;
        }

        // Includes equal finite numbers, ±0.0, and infinities of the same sign.
        if (a == b) {
            return true;
        }

        // If an infinity remains that was not equal, reject it.
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }

        double difference = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        double limit = Math.max(absTol, relTol * scale);

        return difference <= limit;
    }

    public static void main(String[] args) {
        double absTol = 1e-9;
        double relTol = 1e-9;

        System.out.println("0.1 + 0.2 == 0.3: " + (0.1 + 0.2 == 0.3));
        System.out.println("decimal close: "
                + isClose(0.1 + 0.2, 0.3, absTol, relTol));
        System.out.println("near zero small: "
                + isClose(0.0, 1e-10, absTol, relTol));
        System.out.println("near zero large: "
                + isClose(0.0, 1e-7, absTol, relTol));
        System.out.println("large values close: "
                + isClose(1e6, 1e6 + 1e-4, absTol, relTol));
        System.out.println("large values far: "
                + isClose(1e6, 1e6 + 1e-2, absTol, relTol));
        System.out.println("NaN: "
                + isClose(Double.NaN, Double.NaN, absTol, relTol));
        System.out.println("same infinity: "
                + isClose(Double.POSITIVE_INFINITY,
                          Double.POSITIVE_INFINITY, absTol, relTol));
        System.out.println("infinity vs finite: "
                + isClose(Double.POSITIVE_INFINITY,
                          Double.MAX_VALUE, absTol, relTol));
        System.out.println("signed zeros: "
                + isClose(-0.0, +0.0, absTol, relTol));
        System.out.println("opposite extremes: "
                + isClose(-Double.MAX_VALUE,
                          Double.MAX_VALUE, absTol, relTol));
    }
}
```

Run with JDK 17 or later:

```bash
javac ApproximatelyEqual.java
java ApproximatelyEqual
```

Output:

```text
0.1 + 0.2 == 0.3: false
decimal close: true
near zero small: true
near zero large: false
large values close: true
large values far: false
NaN: false
same infinity: true
infinity vs finite: false
signed zeros: true
opposite extremes: false
```

This function takes already-computed `double` values. It **does not repair or restore precision** lost in a calculation. Returning `true` merely indicates that the pair of values **meets the specified tolerance criterion**.

### Why Check `NaN` and Infinity First?

`NaN` has the property `Double.NaN == Double.NaN` is `false`; subtracting `NaN` also gives `NaN`. Every `NaN <= limit` comparison returns `false`. Nevertheless, checking explicitly expresses the policy accurately and prevents accidental behavior changes when modifying the algorithm.

`Infinity - Infinity` produces `NaN`; so if you only compute `Math.abs(a-b)`, two infinities of the same sign would be reported as unequal. The example deliberately recognizes them via `a == b`. For simulation or sensor data, an application might also want to **reject all non-finite values** upfront; in that case, replace the `a == b` policy with a `Double.isFinite` check first. The policy must be clearly documented in the API.

### Subtraction Can Overflow to Infinity

With `a = Double.MAX_VALUE` and `b = -Double.MAX_VALUE`, both are finite numbers, yet `a-b` exceeds the finite magnitude of `double`, so `difference` becomes `+Infinity`. The function returns `false`, which is right for the valid thresholds noted above (`relTol < 1`, finite `absTol`). This is why the function avoids dividing `difference` by `scale` to form a ratio: the intermediate operation can overflow, leading to hard-to-explain results.

Even with this case guarded, do not treat the formula as an arbitrary exact distance algorithm over the entire `double` domain. It is an **acceptance rule for approximate equality** based on `double` arithmetic and application tolerances.

## 5. Choosing `absTol` and `relTol` Based on Data

Before deciding on tolerances, you need to know typical magnitudes, units, and error sources.

### 5.1. Absolute Error Carries Units

Suppose two distance calculation results in meters are considered equivalent if they differ by at most `0.001 m`. Then `absTol = 0.001` has a business basis. If you convert the results to millimeters, that same tolerance must be converted to `1.0 mm`. Never keep the numerical value `0.001` when changing units.

For tiny values, if `absTol` is too large, many genuinely distinct values will be treated as close to 0. One way to pick a threshold is from measurement device resolution, source data accuracy, or known analytical error.

### 5.2. Relative Error Scales with Magnitude

If results on the scale of millions can fluctuate by a few parts per billion due to the algorithm, a `relTol` set according to the expected error level can make more sense than an extremely small absolute threshold.

For example, `relTol = 1e-9` permits a deviation of about `0.001` at scale `1e6`. However, that does **not** automatically prove a `0.001` discrepancy is acceptable for asset counts, money, or IDs. Consult domain rules before picking numbers.

### 5.3. Exact Threshold of 0

If you set `absTol = 0.0` and `relTol = 0.0`, the function in Section 4 accepts almost only pairs that are **numerically equal**: it still treats `+0.0` and `-0.0` as equal, treats same-sign infinities as equal, and rejects `NaN`. This differs from requiring matching **bit patterns**.

Do not use a 0 threshold if the goal is to allow ordinary rounding error.

### 5.4. Do Not Use Machine Epsilon as an Arbitrary Threshold

`Math.ulp(1.0)` for `double` is approximately `2.220446049250313E-16`. This is the spacing between `1.0` and the next `double`, not a reasonable "universal tolerance" across the entire range.

One ULP varies with value magnitude: `Math.ulp(1e16)` is `2.0`. Meanwhile, `Double.MIN_VALUE` is the **smallest positive non-zero** number, not a machine error to use for every comparison. When choosing thresholds by ULP count, account for precision changes across domains, subnormal numbers, and business logic; that serves a different purpose from pure `absTol`/`relTol`.

## 6. Comparing Against a Reference Value vs. Symmetric Comparison

There are two different scenarios:

**One side is a more trustworthy reference.** For instance, a simulation uses a high-precision result as a standard `reference` and evaluates `actual`. Then the criterion:

\[
|\text{actual}-\text{reference}|
\le \max(\text{absTol},\text{relTol}\cdot|\text{reference}|)
\]

can accurately reflect "error measured relative to the standard scale." However, you need an explicit policy for `reference == 0` and non-finite data. If values can be huge and prone to overflow, design an appropriate comparison method.

**Both sides are peers.** When cross-checking results from two implementations without designating either as the standard, the symmetric criterion with `max(|a|,|b|)` lets you swap the two arguments without changing the verdict.

Either criterion may accept one pair of numbers while rejecting another compared to the other criterion. Do not change the denominator when implementing a specific test standard or API contract.

### The "Nearly Equal" Relation Is Not Transitive

With `absTol = 0.1` and `relTol = 0`, consider `a = 0.0`, `b = 0.09`, and `c = 0.18`:

- `a` is close to `b` because the difference `0.09 <= 0.1`.
- `b` is close to `c` because the difference `0.09 <= 0.1`.
- `a` is **not** close to `c` because the difference `0.18 > 0.1`.

Therefore, "approximately equal" **is not a mathematical equivalence relation**, even though the function is symmetric and returns `true` for two identical finite numbers. Do not use this function as `equals`/`hashCode`, as the uniqueness definition for `HashSet`/`HashMap`, or as a `Comparator` for sorting keys: those structures require different contracts, and non-transitive closeness can break consistency.

If a problem needs to group nearby values, define an explicit grouping rule (for example, binning intervals at a specified resolution) instead of treating `isClose` as object equality.

## 7. `==`, `Double.compare`, `BigDecimal.compareTo`, and Approximate Comparison

These operations have different purposes:

| Comparison method | Goal | Key characteristics to remember |
| --- | --- | --- |
| `a == b` for `double` | Equality under Java arithmetic operators | `+0.0 == -0.0` is `true`; `NaN == NaN` is `false` |
| `Double.compare(a, b)` | Consistent ordering to compare/sort `double` per `Double` contract | Distinguishes `-0.0` from `+0.0`; treats `NaN`s as equal in this comparison |
| `isClose(a, b, absTol, relTol)` | Accepting discrepancy within application thresholds | Not transitive; do not use in place of `equals`/`Comparator` |
| `BigDecimal.compareTo` | Comparing decimal numeric value of `BigDecimal` | `new BigDecimal("2.0").compareTo(new BigDecimal("2.00")) == 0` |
| `BigDecimal.equals` | Equality of both value and `scale` per `BigDecimal` contract | `"2.0"` and `"2.00"` are not equal under `equals` |

Do not convert from `double` to `BigDecimal` after a calculation has already lost source information and expect the result to magically become exact. If business logic needs exact decimals (such as money), keep inputs as decimal strings or represent integers in the smallest appropriate unit.

Nor should you assume every `double` calculation needs approximate comparison. Explicit sentinel checks, status flags, exactly represented integers, or values where the API contract requires exactness can use direct comparison. Choose the comparison kind by **data meaning**.

## 8. Reasonable Testing for Tolerance-Based Comparisons

A valuable test suite should cover edge cases that are easily overlooked:

1. **Representation error:** `0.1 + 0.2` compared with `0.3`.
2. **Very close to 0:** `0` vs. amounts smaller and larger than `absTol`.
3. **Large scale:** difference small relatively yet larger than `absTol`.
4. **Outside threshold:** pairs differing by more than both tolerances.
5. **Negative signs:** two close negative numbers, or a negative and positive number near 0; use `Math.abs` to check magnitude.
6. **Two zeros with opposite signs:** explicit `+0.0`/`-0.0` policy.
7. **`NaN` and infinity:** policy must align with callers.
8. **Extreme values:** avoid intermediate subtraction or division producing unexpected `Infinity`/`NaN`.
9. **Invalid tolerances:** negative values, `NaN`, infinity, or `relTol` outside the allowed configuration range.
10. **Exactly at the threshold:** understand the effect of `<` vs. `<=` and error when representing the threshold itself.

To test the core of the function above, you can try:

```java
// These lines are inside a Java method; this example uses
// ApproximatelyEqual.isClose defined in full in Section 4.
boolean nearZero = ApproximatelyEqual.isClose(
        0.0, 1e-10, 1e-9, 1e-9);      // true

boolean farNearZero = ApproximatelyEqual.isClose(
        0.0, 1e-7, 1e-9, 1e-9);       // false

boolean largeClose = ApproximatelyEqual.isClose(
        1e6, 1e6 + 1e-4, 1e-9, 1e-9); // true
```

For scientific pipelines needing accuracy evaluation, also record absolute error, relative error (when the denominator is meaningful), reference value, ULP count if relevant, and the rationale for choosing the threshold. A boolean `true`/`false` alone does not provide enough information to diagnose algorithm quality.

## 9. Common Mistakes

### Using Only an Absolute Threshold for All Values

```java
Math.abs(a - b) < 1e-9
```

This can be a reasonable rule if all data shares a known unit and scale. However, when comparing from values near 0 up to millions, it does not scale with magnitude. You can add `relTol` to reflect proportional error.

### Using Only a Relative Threshold Around 0

```java
Math.abs(a - b) <= relTol * Math.max(Math.abs(a), Math.abs(b))
```

With one side equal to 0 and the other non-zero, if `0 <= relTol < 1`, the condition can never be true. This may be overly strict if the problem permits tiny absolute discrepancies. Add `absTol` when practically needed.

### Dividing to Compute a Ratio Without Considering 0 and Overflow

The expression `Math.abs(a-b) / Math.abs(b)` breaks when `b = 0` and can produce infinity/`NaN` for special inputs or differences. Comparing by multiplying the threshold with the magnitude scale usually avoids division in simple conditions, yet still requires checking finiteness.

### Unintentionally Accepting `NaN` or Infinity

Do not rely on a short algebraic expression to determine policy. Explicitly handle `Double.isNaN`, `Double.isFinite`, and same-sign infinity if the application intends to treat them as equal.

### Picking a Fixed "EPSILON" Because It Appeared in an Example

Values like `1e-6`, `1e-9`, and `1e-12` have no universal validity. Derive them from requirements, units, input resolution, and algorithmic error. An `absTol` that is too large treats business-distinct values as equal; a `relTol` that is too small makes tests fail easily on valid error.

### Using Approximate Comparison for Identifiers and Data Structures

IDs, integer timestamps, sequence numbers, array indices, and identifier keys require exact criteria. If two IDs differ by one unit, using `relTol` can cause them to be treated as "equal" at large magnitudes, breaking logic.

### Forgetting That Error Happened Before Comparison

If two different large integers were already rounded to the same `double`, both `==` and `isClose` can return `true`; no comparison can recover lost source precision. When you need to distinguish large consecutive integers, keep them as `long` or `BigInteger`.

### Confusing Closeness with Algorithm Correctness

A result can fall within tolerance and still be logically wrong. Numerical testing must also verify invariants, value domains, conditional branches, and comparisons with trusted results—not merely loosen thresholds until every test passes.

## 10. Self-Check Exercises

**Question 1.** Given `absTol = 1e-8` and `relTol = 1e-6`, do `a = 0` and `b = 5e-9` satisfy the `max`-form condition? What about `b = 5e-7`?

**Answer:** `5e-9` passes because it is less than the absolute threshold `1e-8`. `5e-7` fails: the relative threshold is only `1e-6 × 5e-7 = 5e-13`, while the absolute threshold is `1e-8`.

**Question 2.** Given `absTol = 1e-8` and `relTol = 1e-6`, are `a = 1_000_000` and `b = 1_000_000.5` close?

**Answer:** Yes. The absolute difference is `0.5`, while the relative threshold is about `1.0000005`, which is greater than `0.5`.

**Question 3.** Why is a separate branch needed for same-sign infinities in the approximate comparison function?

**Answer:** `Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY` is `true`, whereas `Infinity - Infinity` gives `NaN`; using only `Math.abs(a-b) <= limit` would conflict with a policy that treats two same-sign infinities as equal.

**Question 4.** Can `isClose` be used as `equals` logic for `HashMap` keys?

**Answer:** No. Approximate equality may lack transitivity; it does not satisfy the equality contract needed to define keys consistently. Use normalized/representative values and `equals`/`hashCode` matching your identity policy.

**Question 5.** When should you use tolerance based on `reference` instead of `max(|a|, |b|)`?

**Answer:** When one side is an independently meaningful standard and error requirements are specified as a proportion of the standard value. You must specify how `reference = 0` is handled; if both sides are peers, the symmetric formula is easier to explain.

**Question 6.** Can approximate comparison prove that `0.1 + 0.2` was computed mathematically exactly?

**Answer:** No. It only checks that the discrepancy falls within a chosen tolerance. Binary values are still rounded; to require exact decimal digits from the source, use an appropriate representation and calculation rules such as `BigDecimal` from decimal strings.

**Remember:** Absolute error answers *"how far off in data units?"*; relative error answers *"how far off relative to scale?"*. Combining them via `|a-b| <= max(absTol, relTol × max(|a|,|b|))` often fits data spanning multiple scales, yet thresholds and `NaN`/infinity policies must still be decided by the problem. Approximate comparison is a result-acceptance rule—it does not replace exact values, the `equals` contract, or algorithmic error analysis.
