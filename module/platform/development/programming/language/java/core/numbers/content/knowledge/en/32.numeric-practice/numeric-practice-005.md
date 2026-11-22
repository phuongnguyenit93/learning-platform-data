# Building an Approximate Equality Function with a Clear Contract in Java

## 1. Practice Objectives

In Java, `float` and `double` use finite binary representations according to IEEE 754. Many familiar decimal numbers, such as `0.1` or `0.2`, cannot be represented exactly in a finite number of bits. Thus the operation:

```java
double value = 0.1 + 0.2;
System.out.println(value);       // 0.30000000000000004
System.out.println(value == 0.3); // false
```

produces a result different from decimal intuition. Sometimes a problem allows two values with a very small discrepancy to be treated as **approximately equal**, such as when comparing measurements, simulations, or floating-point calculations with a specified tolerance.

However, saying "nearly equal if the difference is small enough" is not enough to implement: **small enough compared to what, what happens near 0, are infinities/NaN handled, and how are invalid values treated?** A comparison function needs an explicit **contract** and boundary tests.

This lesson builds a Java 17+ function for `double` with **absolute tolerance** and **relative tolerance**, handling `NaN`, `Infinity`, `+0.0`/`-0.0`, avoiding overflow in subtraction; it also points out mathematical limitations that prevent an approximate-equality function from replacing `equals()` or `compareTo()`.

## 2. Choose the Formula and Semantics Before Writing Code

Let the two numbers to compare be \(a\) and \(b\). For finite numbers, we define:

\[
\Delta = |a-b|,\qquad
S = \max(|a|,|b|),\qquad
T = \max(\mathrm{absTol}, \mathrm{relTol}\times S)
\]

The function returns **`true` if and only if** \(\Delta \le T\), after handling `NaN`, infinity, and exact equality per the contract.

- **`absTol`:** maximum absolute error in the **units of the quantity**. For example, a measurement in meters may allow an error of `0.001` meters.
- **`relTol`:** allowable error ratio relative to the magnitude of the two values, e.g., `1e-9` is one part per billion. This ratio is **dimensionless**.
- **`max(absTol, relTol × S)`:** permits deviation under **either condition** (absolute or relative). This is a **policy choice in this lesson**, not the only definition of "nearly equal."

Choosing `max` means:

```text
abs(a - b) <= absTol
                 OR
abs(a - b) <= relTol * max(abs(a), abs(b))
```

Some libraries use `absTol + relTol × S` or other forms. The two formulas differ near the boundary, so one cannot be arbitrarily substituted for the other without updating the contract and tests.

### Why combine both kinds of tolerance?

With **absolute error** alone:

```text
abs(a-b) <= 0.001
```

it makes sense if all results have a fixed scale, yet can be too tight for numbers around a billion and too loose for numbers around a billionth.

With **relative error** alone:

```text
abs(a-b) <= 1e-9 * max(abs(a), abs(b))
```

it scales with the magnitude of values, yet near `0`, `S` approaches `0` and the relative threshold also approaches `0`. Therefore, a domain-meaningful absolute threshold is needed to decide "close enough to 0."

For example, `absTol = 1e-9`, `relTol = 0` treats `0.0` and `1e-12` as nearly equal. Meanwhile, `absTol = 0`, `relTol = 1e-9` only accepts values sufficiently close proportionally, providing no absolute "safe zone" around 0.

## 3. Contract of the Function to Implement

The function has the signature:

```java
static boolean nearlyEqual(
        double a, double b, double absTol, double relTol)
```

Explicit contract:

1. Both parameters `a`, `b` can be any `double` value, including finite numbers, `+0.0`, `-0.0`, both infinities, and `NaN`.
2. `absTol` must be **finite and non-negative**. `0.0` is accepted; `NaN`, infinities, and any negative number are rejected.
3. `relTol` must be **finite and in `[0, 1)`**. The `< 1` constraint is a contract decision so relative tolerance is always under 100% of the reference magnitude; real applications should choose much smaller values.
4. **`NaN` in either operand → `false`**, even when both are NaN.
5. If `a == b` under Java's primitive comparison → **`true`**. Thus infinities of the same sign return `true`, and `+0.0` is nearly equal to `-0.0`.
6. If only one operand is infinite, or they are infinities of opposite signs → **`false`**. Do not try to compute finite errors for infinities.
7. For the remaining two finite numbers, compute \(\Delta\), \(S\), \(T\) per Section 2 and return `true` when \(\Delta \le T\). **Exact equality with the threshold is also accepted**.
8. With invalid tolerances, throw `IllegalArgumentException` **before inspecting the data**. That means even `nearlyEqual(1, 1, NaN, 0)` still throws: misconfiguration must never be silently ignored.

Tolerance constraints and behavior for special values are design decisions. Another system might treat NaN as an input error and throw an exception, or require all inputs to be finite. What matters is **publishing the policy** and testing it, rather than letting behavior arise accidentally from Java operators.

## 4. Java 17+ Implementation: Usable and Testable Version

Save the entire file as **`NearlyEqualDemo.java`**:

```java
public class NearlyEqualDemo {

    /**
     * Approximate comparison by an absolute-or-relative tolerance:
     * |a - b| <= max(absTol, relTol * max(|a|, |b|)).
     *
     * absTol: finite, >= 0.
     * relTol: finite, 0 <= relTol < 1.
     * NaN: false; same-sign infinities: true;
     * other infinite pairs: false; +0 and -0: true.
     */
    public static boolean nearlyEqual(
            double a, double b, double absTol, double relTol) {

        if (!Double.isFinite(absTol) || absTol < 0.0
                || !Double.isFinite(relTol)
                || relTol < 0.0 || relTol >= 1.0) {
            throw new IllegalArgumentException("invalid tolerances");
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

        double difference = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        double allowed = Math.max(absTol, relTol * scale);
        return difference <= allowed;
    }

    public static void main(String[] args) {
        System.out.println("0.1 + 0.2 ~= 0.3: "
                + nearlyEqual(0.1 + 0.2, 0.3, 1e-12, 0.0));

        System.out.println("large relative pass: "
                + nearlyEqual(
                        1_000_000_000.0, 1_000_000_001.0, 0.0, 1e-9));
        System.out.println("large relative fail: "
                + nearlyEqual(
                        1_000_000_000.0, 1_000_000_002.0, 0.0, 1e-9));
        System.out.println("near zero absolute: "
                + nearlyEqual(0.0, 1e-12, 1e-9, 0.0));

        System.out.println("zero tolerances require exact equality: "
                + nearlyEqual(1.0, Math.nextUp(1.0), 0.0, 0.0));
        System.out.println("one ulp accepted: "
                + nearlyEqual(
                        1.0, Math.nextUp(1.0), Math.ulp(1.0), 0.0));

        System.out.println("signed zeros: "
                + nearlyEqual(+0.0, -0.0, 0.0, 0.0));
        System.out.println("same infinities: "
                + nearlyEqual(
                        Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, 0.0, 0.0));
        System.out.println("different infinities: "
                + nearlyEqual(
                        Double.POSITIVE_INFINITY,
                        Double.NEGATIVE_INFINITY, 0.0, 0.0));
        System.out.println("NaNs: "
                + nearlyEqual(Double.NaN, Double.NaN, 1.0, 0.1));

        System.out.println("overflowing difference: "
                + nearlyEqual(
                        Double.MAX_VALUE, -Double.MAX_VALUE,
                        Double.MAX_VALUE, 0.5));

        double sub = Double.MIN_VALUE;
        System.out.println("subnormal exact-only: "
                + nearlyEqual(0.0, sub, 0.0, 0.0));
        System.out.println("subnormal with absTol: "
                + nearlyEqual(0.0, sub, sub, 0.0));

        boolean ab = nearlyEqual(0.0, 0.75, 1.0, 0.0);
        boolean bc = nearlyEqual(0.75, 1.5, 1.0, 0.0);
        boolean ac = nearlyEqual(0.0, 1.5, 1.0, 0.0);
        System.out.println(
                "not transitive: " + ab + ", " + bc + ", " + ac);

        try {
            nearlyEqual(1.0, 1.0, Double.NaN, 0.0);
            System.out.println("invalid tolerance: accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid tolerance: rejected");
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac NearlyEqualDemo.java
java NearlyEqualDemo
```

Output:

```text
0.1 + 0.2 ~= 0.3: true
large relative pass: true
large relative fail: false
near zero absolute: true
zero tolerances require exact equality: false
one ulp accepted: true
signed zeros: true
same infinities: true
different infinities: false
NaNs: false
overflowing difference: false
subnormal exact-only: false
subnormal with absTol: true
not transitive: true, true, false
invalid tolerance: rejected
```

### Explaining the order of checks

**Check tolerances first:** if `absTol` were `NaN` and we passed it directly to `Math.max`, the comparison result could be affected unpredictably. Worse, an equal-values branch could mask a bad configuration. Therefore, validation is the first step.

**NaN before equality operator:** in Java, `Double.NaN == Double.NaN` is `false`. Handling it explicitly makes clear this is a policy decision, rather than an accidental reliance on the operator.

**Exact equality before infinity check:** `Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY` is `true`; signed zeros of opposite signs are also `==`. Do not compute `Infinity - Infinity` and compare, because such a difference can produce `NaN`.

**Finite check before computing error:** if at least one infinity remains, `a != b` and the finite-number formula cannot apply, so the function returns `false`.

**Compute threshold then compare:** for two finite numbers, the function uses `difference <= allowed`, accepting exact equality with the threshold as well. `Math.max(Math.abs(a), Math.abs(b))` makes the result **symmetric** when swapping the two operands. Do not use only `Math.abs(a)` as the denominator/scale because swapping arguments could yield a different result.

## 5. Why Can We Write Math.abs(a - b) Here?

A common mistake is claiming the difference of two finite `double` numbers is always finite. That is false: with `a = Double.MAX_VALUE` and `b = -Double.MAX_VALUE`, the expression `a - b` **overflows to `+Infinity`**, even though both operands are finite.

The function above handles that case via its specific contract:

- `absTol` must be **finite**, so it is no larger than `Double.MAX_VALUE`.
- `relTol < 1` and `scale` is finite, so `relTol * scale` remains finite and does not exceed `Double.MAX_VALUE`.
- If `Math.abs(a-b)` becomes `Infinity`, the true difference exceeds the finite range of `double`, and **cannot be less than or equal to the chosen finite threshold**. Thus `Infinity <= allowed` is `false` and aligns with this policy.

This explains why the function **does not need to pretend to subtract exactly with BigDecimal** for every case. However, floating-point subtraction still rounds. If you must prove exact error bounds in terms of mathematical real numbers, you must consider input representation and the problem specification; the function above has a contract based on **actual double values and double arithmetic**.

Do not replace it with the expression:

```java
Math.abs(a / b - 1.0) <= relTol
```

without handling `b == 0`, negative signs, underflow, overflow, and symmetry. Division can be undefined or produce infinity; choosing scale via `max(abs(a), abs(b))` is a cleaner rule for the chosen contract.

## 6. Choosing Tolerance Thresholds from the Problem Domain

The values `1e-12`, `1e-9` in the program are **illustrative values**, not safe default tolerances for every system. A suitable threshold must come from at least one of these factors:

- **Units and input resolution:** a temperature sensor with ±0.1°C accuracy does not need a `1e-15` °C tolerance.
- **Accepted error limits:** if the system defines that results differ by at most 0.01 units, `absTol = 0.01` has concrete business meaning.
- **Magnitude variation:** results may span from millionths to billions; `relTol` is useful when allowed error scales with magnitude.
- **Algorithmic error accumulation:** after many additions/multiplications, rounding error can accumulate depending on the algorithm, operation order, and *numerical conditioning*.
- **Need for exact verification:** for currency or integer identifier data, an arbitrary approximate-equality threshold can hide critical bugs.

### Example of an absolute threshold

If two sensors both measure length in meters and the requirement is "differ by at most `0.002` meters," the function can be called as:

```java
boolean close = nearlyEqual(measuredA, measuredB, 0.002, 0.0);
```

This is a threshold **defined in meters**, applied uniformly across the value domain. Do not use `0.002` if the values are in millimeters without converting units accordingly.

### Example of a relative threshold

If the requirement is "differ by less than one part per million of the value's magnitude," you can choose `relTol = 1e-6` and a small `absTol` appropriate near 0. When `a` and `b` are around one million, the relative threshold is about 1 unit; when values are around one millionth, the relative threshold is only around `1e-12`.

The lesson's formula uses **`<=`**, so "under one part per million" should be stated precisely in the contract as **not exceeding the threshold**. If the requirement truly means "strictly less than," change the operator and update boundary tests.

### Zero tolerance

When `absTol = 0` and `relTol = 0`, two finite numbers must have a computed difference of 0 to be nearly equal; for ordinary finite numbers, this is equivalent to `==`. Under the current policy, `+0.0` and `-0.0` are equal, two infinities of the same sign are equal, and NaN is not nearly equal to itself.

If **bit-pattern comparison** is required, use `Double.doubleToRawLongBits` in a separate check; that is a completely different contract from numerical approximate equality.

## 7. Testing by Equivalence Classes and Boundary Values

An approximate-equality function must be tested against its **contract**, not just with `0.1 + 0.2`. Minimum test groups:

| Group | Example | Expected per contract |
|---|---|---|
| Exact finite equality | `(1.0, 1.0, 0, 0)` | `true` |
| Small decimal discrepancy | `(0.1+0.2, 0.3, 1e-12, 0)` | `true` |
| Exceeds absolute threshold | `(0, 0.02, 0.01, 0)` | `false` |
| Near 0 | `(0, 1e-12, 1e-9, 0)` | `true` |
| Large numbers, sufficient relative threshold | `(1e9, 1e9+1, 0, 1e-9)` | `true` |
| Large numbers, insufficient relative threshold | `(1e9, 1e9+2, 0, 1e-9)` | `false` |
| Zero tolerance | `(1, Math.nextUp(1), 0, 0)` | `false` |
| One ULP at 1 | `(1, Math.nextUp(1), Math.ulp(1), 0)` | `true` |
| Two signed zeros | `(+0.0, -0.0, 0, 0)` | `true` |
| Two positive infinities | `(+∞, +∞, 0, 0)` | `true` |
| Opposite-sign infinities | `(+∞, -∞, 0, 0)` | `false` |
| NaN | `(NaN, NaN, 1, 0.1)` | `false` |
| Overflowing double difference | `(MAX_VALUE, -MAX_VALUE, MAX_VALUE, 0.5)` | `false` |
| Subnormal near 0 | `(0, MIN_VALUE, 0, 0)` | `false` |
| Subnormal with tolerance | `(0, MIN_VALUE, MIN_VALUE, 0)` | `true` |
| Invalid tolerance | `absTol = NaN`; `relTol = 1`; `absTol < 0` | Throws `IllegalArgumentException` |

`Double.MIN_VALUE` is the **smallest positive non-zero `double`** (subnormal), not the negative number with largest magnitude. `Double.MAX_VALUE` is the largest finite positive number. Do not confuse these two constants when designing tests.

### Testing symmetry

The function is defined symmetrically: `nearlyEqual(a,b,t,r)` must equal `nearlyEqual(b,a,t,r)` for the same valid tolerances. Using `max(abs(a),abs(b))` preserves this property. If you use `relTol * abs(a)` alone and treat `a` as the reference, that is a **directional comparison**; it has valid uses too, but must be clearly documented and not called a symmetric relation.

### Testing near boundaries with nextUp and nextDown

Use `Math.nextUp(x)` and `Math.nextDown(x)` to obtain the adjacent representable `double` value in real-number order, instead of adding `1e-16` and assuming the value actually changes. `Math.ulp(x)` gives the ULP spacing in that region (mindful of exponent boundaries).

For example, `Math.nextUp(1.0)` differs from `1.0` by one `Math.ulp(1.0)` step. With `absTol = 0` and `relTol = 0`, the function must return `false`; with `absTol = Math.ulp(1.0)`, it returns `true`.

**Do not assume N ULPs is the same as a fixed business error.** ULP measures binary representation structure and varies with magnitude; choosing ULP as a criterion must come from algorithm analysis, not unconditionally replacing absolute/relative thresholds.

## 8. Important Mathematical Properties and Limitations

### Approximate equality is not transitive

A standard equality relation requires transitivity: if A equals B and B equals C, then A must equal C. Tolerance-based approximate equality **lacks** this property.

With `absTol = 1.0` and `relTol = 0`:

```text
a = 0.00
b = 0.75
c = 1.50

|a - b| = 0.75 <= 1.0 => nearly equal
|b - c| = 0.75 <= 1.0 => nearly equal
|a - c| = 1.50 >  1.0 => NOT nearly equal
```

Thus `nearlyEqual(a,b) == true` and `nearlyEqual(b,c) == true` do not imply `nearlyEqual(a,c) == true`. The function in this lesson is also **not reflexive for NaN**, because the policy deliberately treats any comparison involving NaN as false.

**Consequence:** do not use approximate equality as the basis for implementing `Object.equals()`/`hashCode()` for objects placed in a `HashSet` or used as `HashMap` keys. Also do not use it to return `0` in a `Comparator` for `TreeSet`/`TreeMap` or sorting algorithms: comparators need a consistent ordering contract; non-transitivity can cause bugs or unpredictable behavior.

If you need to **group** numbers at a fixed resolution, choose a partitioning/quantization rule with clearly defined boundaries, or build a clustering algorithm with its own contract. Those techniques have different semantics and can create differences at bucket boundaries.

### Threshold depends on compared values

With `max(absTol, relTol × max(abs(a), abs(b)))`, a very large `b` can make the relative tolerance large. For instance, `relTol = 0.5` allows discrepancies up to 50% of the reference magnitude; mathematically the contract remains consistent, yet most applications would consider such a threshold far too wide.

The technical limit `relTol < 1` prevents configuring 100% or more, **not proving** a smaller tolerance is appropriate. You must enforce domain-specific limits: e.g., at most `1e-6` if required by the contract.

### There is no "one epsilon for all doubles"

`Double.MIN_VALUE` is not a suitable epsilon for all calculations; the spacing between representable values grows with magnitude. `Math.ulp(1.0)` reflects the step near 1, whereas `Math.ulp(1e12)` is much larger. A threshold of `1e-9` can be too strict in large-magnitude ranges yet too permissive in very small-magnitude ranges. Practical policy must consider units, number of operations, algorithm sensitivity, and acceptable error levels.

### Precision is a different concept from tolerance

`double` has finite binary precision (53 significant bits for normalized numbers); this is a representation limit. `absTol` and `relTol` are **policies for accepting discrepancy** when comparing results. They are related in error analysis, yet are not the same concept.

For example, an ill-conditioned operation can amplify input error by many ULPs. Output tolerance must be based on valid error bounds of the **entire algorithm**, not simply plugging in `Math.ulp(1.0)` everywhere.

## 9. When Do You Need BigDecimal or Exact Comparison?

For **money, rates defined to a fixed number of decimal places, or legal/business rounding rules**, approximate `double` comparison can hide differences that must be detected. If the data is exact decimal, consider `BigDecimal` constructed from strings:

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.00");
BigDecimal b = new BigDecimal("1.0");

// Compare numeric value; do not require matching scale for equality:
boolean sameNumericValue = a.compareTo(b) == 0; // true

// If maximum allowed decimal deviation is 0.01:
BigDecimal tolerance = new BigDecimal("0.01");
boolean withinAbsoluteTolerance =
        a.subtract(b).abs().compareTo(tolerance) <= 0; // true
```

This is an **illustrative code snippet for use inside a method or class**; it has no standalone `main()`. `BigDecimal.compareTo()` compares numeric values, whereas `BigDecimal.equals()` also considers scale; for example, `"1.00"` and `"1.0"` have equal value, yet `equals()` returns false.

When applying tolerances with `BigDecimal`, set value/resource limits, specify scale/precision, define rounding rules if calculations do not terminate in decimal representation, and decide whether rounding occurs before or after comparison. Do not silently convert `BigDecimal` to `double` just to use `nearlyEqual` when decimal accuracy is required.

When comparing **integers** (`int`, `long`, `BigInteger`), values are already represented exactly within the type's range; exact equality is usually more appropriate. If you want to allow a difference of N integer units, define the range explicitly and watch for overflow when computing the difference, without converting integers larger than \(2^{53}\) to `double`.

## 10. Common Implementation Mistakes

### Writing only Math.abs(a - b) < 1e-9

This approach does not state units, excludes **exact boundary equality** due to `<`, lacks magnitude-relative scaling, and does not specify NaN/infinity behavior. It may suffice for a tiny check with a bounded scale, but not for a shared API with a complete contract.

### Using relTol * a instead of a symmetric scale

If only `a` is used as the baseline, swapping parameters can change the result. Some problems intentionally distinguish **expected value** from **measured value**; in that case, relative error against `expected` is valid if the contract states each argument's role. However, if the function name implies symmetric comparison of two numbers, `max(abs(a), abs(b))` keeps that property clear.

### Using Infinity as a tolerance to "toggle" checks

If `absTol = Infinity`, far-apart values can be treated as unconditionally equal and produce surprising results with special values. This lesson's function **rejects infinite and NaN tolerances** to prevent configurations from hiding bugs. To disable one condition, pass `0` for that parameter and explicitly choose the other per business rules.

### Forgetting NaN and signed zero rules

`Double.NaN == Double.NaN` is false, whereas `Double.compare(Double.NaN, Double.NaN) == 0` has different semantics. `+0.0 == -0.0` is true, even though `Double.doubleToRawLongBits` yields two distinct bit patterns. An approximate-equality function should specify **arithmetic semantics** vs. **bit semantics** from the start.

### Failing to guard against overflowing difference

Two finite numbers can have an infinite difference. If you write a relative formula that divides by the difference, or use an infinite tolerance, bugs can go unnoticed. In this lesson's function, `difference == Infinity` naturally evaluates to false because `allowed` is finite, which follows directly from the `relTol < 1` contract.

### Taking the average of two numbers for scale

Writing `scale = Math.abs((a+b)/2)` can overflow in `a+b`, or approach 0 when two large values have opposite signs, skewing the threshold. `max(abs(a),abs(b))` avoids intermediate addition and preserves symmetry per the chosen definition.

### Rounding strings and then comparing

Formatting with `String.format("%.2f", value)` only controls **display**, and can make two different numbers look identical or vary with locale. Comparing formatted strings cannot replace a numeric tolerance contract; if business rules require rounding to 2 decimal places, define the exact rounding operation and when it occurs before comparing.

### Applying to data that already lost precision unknowingly

A large `long` can lose digits when converted to `double`. Then `nearlyEqual` compares **two post-conversion double values**, not recovering the original integer data. Similarly, money passed through `double` may have already lost exact decimal information. Verify the data source before choosing a comparison strategy.

## 11. Practice Exercise and Acceptance Criteria

Suppose a numeric test suite must accept a deviation of at most `0.001` in the result's units, or `1e-8` of the result's magnitude, whichever yields the larger threshold. Under the chosen contract, the call is:

```java
boolean accepted = nearlyEqual(actual, expected, 0.001, 1e-8);
```

Before using it in an application, clarify the meaning of `actual` and `expected`, measurement units, how the expected value is obtained, and whether **exact boundary equality** is accepted. The function defines a **symmetric** comparison (swapping `actual`/`expected` does not change the result). If acceptance requires "deviation at most X% of expected," write a separate function using **expected as the denominator** and handling `expected == 0`, rather than silently altering this function's formula.

Acceptance tests should include these groups:

1. Exact match; small deviation within threshold; deviation exceeding threshold.
2. Values near 0 where absolute tolerance plays a clear role.
3. Very large values where relative tolerance dominates.
4. Negative numbers, opposite-sign pairs, `+0.0` and `-0.0`.
5. `NaN`, two same-sign infinities, opposite-sign infinities, one finite and one infinite.
6. Invalid tolerances: negative, `NaN`, infinite, `relTol = 1`.
7. Adjacent values via `Math.nextUp`/`nextDown` and subnormal numbers near 0.
8. Example demonstrating lack of transitivity so API users understand approximate equality is **not an equivalence relation**.

### Self-check questions

**1.** Why are `absTol = 0` and `relTol = 1e-9` insufficient for a "nearly equal to 0" check with small absolute measurement error? Because the relative threshold `relTol × max(|a|,|b|)` approaches 0 as both values approach 0; an `absTol` grounded in actual resolution is needed.

**2.** What does `nearlyEqual(Double.POSITIVE_INFINITY, Double.POSITIVE_INFINITY, 0, 0)` return? **`true`**, because the two values are exactly equal under the policy, handled before subtraction could produce NaN.

**3.** Why should `nearlyEqual` not be used in `hashCode`/`equals` for map keys? Because tolerance-based approximate equality is **not transitive**, failing the equivalence contract required by equality-based collections.

**4.** What does `nearlyEqual(0.0, Double.MIN_VALUE, 0, 0)` return? **`false`**, because one number is 0 while the other is a non-zero positive subnormal. If `absTol = Double.MIN_VALUE` is set, it returns **`true`**.

**5.** If computing `a - b` from two finite doubles overflows to infinity, should they be considered nearly equal? **No**. This lesson's contract rejects two differing numbers when their separation exceeds finite limits; `difference <= allowed` evaluates to false.

**Remember:** A sound approximate-equality function must publish its **formula, tolerance meaning, special-value handling, boundary rules, input limits, and tests**. This lesson's contract chooses \(|a-b| \le \max(\mathrm{absTol},\mathrm{relTol}\cdot\max(|a|,|b|))\) for two finite numbers, NaN always false, matching infinities true, signed zeros true, and invalid tolerances throwing an error. Choose thresholds from real requirements and do not use approximate equality to replace exact equality in data structures.
