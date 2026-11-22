# ULP and Spacing Between Adjacent Values in Java

**ULP (Unit in the Last Place)** is a unit that describes **the sparsity of representable floating-point numbers** around a value. Unlike integers, `float` and `double` cannot represent every real number exactly; they have a finite set of bit patterns. As a number's magnitude grows, the spacing between nearby representable values generally increases as well.

A surprising example:

```java
double x = 1.0;
System.out.println(Math.nextUp(x));   // 1.0000000000000002
System.out.println(Math.ulp(x));      // 2.220446049250313E-16
```

When stepping from `1.0` to the `double` immediately above it, the smallest step is about `2.22 × 10^-16`. Around `10^16`, however, one ULP is already **2.0**: adding `1.0` may not produce a new `double`.

It is crucial to distinguish **representation grid spacing**, **error after computation**, and **the decimal precision humans desire**. ULP describes the value grid of a floating-point type, not automatically an error bound for every algorithm.

## 1. Why Do Floating-Point Numbers Have Gaps?

Java's `float` is 32-bit and `double` is 64-bit under the IEEE 754 binary floating-point standard, with sign, exponent, and significand fields. For **normal** finite numbers, the value essentially has the structure:

```text
value = (-1)^sign × (1.fraction)_2 × 2^exponent
```

Fraction bits are finite: `float` has **23 stored fraction bits** (24 effective significand bits, counting the implicit 1 bit), while `double` has **52 stored fraction bits** (53 effective significand bits). Thus, within a fixed exponent interval, there are only finitely many fraction levels; between two consecutive levels lies a **gap**.

| Property | `float` | `double` |
| --- | --- | --- |
| Size | 32 bits | 64 bits |
| Stored fraction bits | 23 | 52 |
| Significand precision bits, including implicit leading bit in normal | 24 | 53 |
| ULP at `1.0` | `2^-23` ≈ `1.1920929E-7` | `2^-52` ≈ `2.220446049250313E-16` |
| Consecutive integers represented exactly up to | `2^24` | `2^53` |

These numbers represent **bits of binary precision**, not a guarantee that an arbitrary value has exactly 7 or 16 accurate decimal digits. For example, `0.1` has no finite binary representation and must be rounded when converted to `double`.

## 2. What Is ULP? Relationship to Adjacent Numbers

At a normal finite value `x`, the ULP is the magnitude of one representation step corresponding to the least-significant bit position of the significand at `x`'s exponent scale. In Java, `Math.ulp(x)` returns a **non-negative** ULP value for `float` or `double`, with special rules at zero, subnormals, infinity, and NaN.

To inspect adjacent values, Java provides:

- `Math.nextUp(x)`: the next representable floating-point value toward **positive infinity**.
- `Math.nextDown(x)`: the next representable value toward **negative infinity**.
- `Math.nextAfter(start, direction)`: steps one representable value from `start` toward `direction`; the `double` overload returns `double`, and the `float`-start overload returns `float`.

These methods let you look directly at **points on the representation grid**, instead of trying to add an arbitrary `epsilon`. For example, set `x = 1.0`:

```text
Math.nextDown(1.0) = 0.9999999999999999
                1.0
Math.nextUp(1.0)   = 1.0000000000000002
```

Here the step **above** is `2^-52`, yet the step **below** is `2^-53`. This is not a bug! `1.0` is an exact **power of 2**, sitting at the boundary between two intervals with different representation densities. Therefore, you should not claim `Math.ulp(x)` always equals **both** `Math.nextUp(x)-x` and `x-Math.nextDown(x)`.

## 3. Spacing Formula for Normal Numbers

For a positive normal `double` `x` in the power-of-two interval:

```text
2^e <= x < 2^(e+1)
```

the step between consecutive normal numbers **within the same exponent interval** is:

```text
ULP_double(x) = 2^(e - 52)
ULP_float(x)  = 2^(e - 23)
```

For `float`, replace 52 with 23. The formula describes significand spacing; it does not state that every real number in the interval can be stored, nor that operation results are always off by at most one ULP.

Example table for `double`:

| Position | `Math.ulp(x)` | Meaning |
| --- | --- | --- |
| `x = 0.5` | `2^-53` | Denser spacing than around `1.0` |
| `x = 1.0` | `2^-52` | Upward step is `2^-52` |
| `x = 2.0` | `2^-51` | Step doubles upon crossing 2 |
| `x = 1024.0` | `2^-42` | Each step is larger than steps around 1 |
| `x = 2^53` | `2` | Can no longer represent every consecutive integer |

The variation of ULP with exponent provides **nearly constant relative accuracy** for normal numbers, while **absolute accuracy decreases as magnitude grows**. Near 1, one step is tiny; at `2^53`, one step is 2; at extreme magnitudes, one step can span countless integers.

**Boundary exception:** for `x = 2^e` in the normal range (excluding certain very low boundaries), the distance from `x` down to the preceding finite number is **half** the upward step, because it falls in the lower exponent interval. `Math.ulp(x)` uses the interval corresponding to `x`, which is the upward interval at this boundary.

## 4. Exact Example Around `1.0`

We have:

```text
nextUp(1.0) - 1.0   = 2^-52 = 2.220446049250313E-16
1.0 - nextDown(1.0) = 2^-53 = 1.1102230246251565E-16
Math.ulp(1.0)       = 2^-52
```

At `1.0`, `Math.ulp(x)` matches the **upward** step, not the **downward** step. This matters when designing algorithms that test numeric proximity: if you assume “one ULP is an equal distance in both directions,” you will be wrong at `2^e` milestones.

To see the fraction bits and exponent clearly, use `Double.toHexString`:

```java
double ulp = Math.ulp(1.0);
System.out.println(Double.toHexString(ulp)); // 0x1.0p-52
```

In a hex floating-point literal, `p-52` indicates the **base-2** exponent. `0x1.0p-52` has value `2^-52`; it is distinct from integer hex literal notation. For `float`, `Float.toHexString(Math.ulp(1.0f))` returns `0x1.0p-23`.

## 5. Exact Integer Representation Limits: `2^24` and `2^53`

Because the significand has finite bits, in `float` every integer from 0 to `2^24` is represented exactly, yet **not every larger integer** can be represented. For `double`, the corresponding threshold is `2^53`.

Example with `double`:

```java
double limit = 0x1.0p53;        // 2^53 = 9007199254740992
double tooSmallToChange = limit + 1.0;
System.out.println(tooSmallToChange == limit); // true
System.out.println(Math.ulp(limit));           // 2.0
```

Both `limit` and `limit + 1.0` evaluate equal in this example. The mathematical number `2^53+1` sits **halfway** between the two representable `double` values `2^53` and `2^53+2`; the default **round to nearest, ties to even** rule rounds it to `2^53`. It is not that “addition was syntactically skipped”; the exact mathematical result lies **off the representation grid**.

Similarly, `Math.ulp(1e16)` is `2.0` and `1e16 + 1.0 == 1e16` evaluates to `true`. For `float` at `2^24`, `Math.ulp(0x1.0p24f)` equals `2.0f`. This explains why `float` should not be used to store identifiers, large integer counters, or values requiring exact unit precision.

## 6. Rounding: Why Adding Half a ULP Can Leave a Value Unchanged

Floating-point addition rounds to a representable number. When the mathematical result lies midway between two adjacent values, the default mode is **nearest, ties to even significand**. Consequently, a change smaller than half the gap near the stored value can vanish.

Example around `1.0`:

```java
double one = 1.0;
double step = Math.ulp(one);
boolean unchanged = (one + step / 2.0) == one; // true under ties-to-even
boolean next = (one + step) == Math.nextUp(one); // true
```

This is an illustrative snippet inside a method. At `1.0`, `step/2.0 = 2^-53` lies halfway between `1.0` and `1.0 + 2^-52`; rounding chooses `1.0`. However, **you cannot generalize this into a rule** that “adding half a ULP never changes anything”: tie-breaking depends on the least-significant bit of the significand and boundary points.

If you repeatedly add a very small delta to a very large sum, small increments can be lost to rounding. When summing data across widely varying magnitudes, consider compensated summation algorithms, sorting/grouping values, or choosing numeric types suited to accuracy requirements.

## 7. Subnormals: Spacing Near Zero

When a number is too small to represent in **normal** form, IEEE 754 provides a **subnormal (denormal)** region whose significand lacks the implicit 1 bit. Consecutive positive subnormals have **uniform** spacing, allowing gradual approach to 0 rather than losing all small values at once.

For Java `double`:

- `Double.MIN_VALUE` is the **smallest nonzero positive `double`**, about `4.9E-324`; **not** the negative number with the largest magnitude.
- `Double.MIN_NORMAL` is the **smallest positive normal**, equal to `2^-1022`.
- The subnormal step is `2^-1074`, which is also `Double.MIN_VALUE`.
- `Math.ulp(0.0)` and `Math.ulp(Double.MIN_NORMAL)` both equal `Double.MIN_VALUE`.

Similarly, `Float.MIN_VALUE` is the smallest positive subnormal `float` (`2^-149`), and `Float.MIN_NORMAL` is the smallest positive normal (`2^-126`). The smallest step in `float`'s subnormal range is `2^-149`.

```java
double stepAtZero = Math.ulp(0.0);             // Double.MIN_VALUE
double firstPositive = Math.nextUp(0.0);        // Double.MIN_VALUE
double firstNegative = Math.nextDown(0.0);      // -Double.MIN_VALUE
```

Both zero forms `+0.0` and `-0.0` exist in IEEE 754; they compare equal via `==`, yet have different sign-bit patterns. `Math.nextUp(-0.0)` still steps to positive `Double.MIN_VALUE`. In the subnormal region, ULP **does not shrink indefinitely**: below the smallest step, a result can round to zero (underflow).

## 8. Special Cases: `NaN`, Infinity, and Largest Finite Value

Not every `double` is an ordinary finite real number. Java has `NaN`, `Double.POSITIVE_INFINITY`, and `Double.NEGATIVE_INFINITY`. Rules of `Math.ulp`:

| Input | `Math.ulp` Result |
| --- | --- |
| `NaN` | `NaN` |
| `+Infinity` or `-Infinity` | `+Infinity` |
| `+0.0` or `-0.0` | `Double.MIN_VALUE` (or `Float.MIN_VALUE`) |
| Nonzero finite value | Positive ULP corresponding to type width |

At `Double.MAX_VALUE`, `Math.ulp(Double.MAX_VALUE)` is still a **very large finite** number, yet `Math.nextUp(Double.MAX_VALUE)` is **`+Infinity`**. Therefore, do not compute “the gap to the next higher finite number” via `nextUp(x)-x` in all cases: at the finite top, **there is no higher finite number**.

Avoid comparing `Math.ulp(Double.POSITIVE_INFINITY)` to a finite arithmetic distance or taking `Math.nextUp(Double.MAX_VALUE) - Double.MAX_VALUE` to infer an ordinary ULP. If using `Math.nextUp`/`nextDown` in numerical algorithms, check `Double.isFinite`, `Double.isNaN`, and `Double.isInfinite` when inputs can be special values.

## 9. Complete Java 17+ Program

Save the file as **`UlpSpacingDemo.java`**:

```java
public class UlpSpacingDemo {
    public static void main(String[] args) {
        double one = 1.0;
        double above = Math.nextUp(one);
        double below = Math.nextDown(one);
        System.out.println("ulp(1.0)=" + Math.ulp(one));
        System.out.println("nextUp(1.0)=" + above);
        System.out.println("nextDown(1.0)=" + below);
        System.out.println("gapAbove=" + (above - one));
        System.out.println("gapBelow=" + (one - below));
        System.out.println("upperGapEqualsUlp=" + (above - one == Math.ulp(one)));
        System.out.println("lowerGapEqualsUlp=" + (one - below == Math.ulp(one)));
        System.out.println("ulpHex=" + Double.toHexString(Math.ulp(one)));
        System.out.println("floatUlpHex=" + Float.toHexString(Math.ulp(1.0f)));
        System.out.println("ulp(0.0)==MIN_VALUE=" + (Math.ulp(0.0) == Double.MIN_VALUE));
        System.out.println("ulp(minNormal)==MIN_VALUE=" + (Math.ulp(Double.MIN_NORMAL) == Double.MIN_VALUE));
        System.out.println("ulp(2.0)/ulp(1.0)=" + (Math.ulp(2.0) / Math.ulp(1.0)));
        System.out.println("ulp(2^53)=" + Math.ulp(0x1.0p53));
        System.out.println("2^53PlusOneLost=" + (0x1.0p53 + 1.0 == 0x1.0p53));
        System.out.println("ulp(1e16)=" + Math.ulp(1e16));
        System.out.println("1e16PlusOneLost=" + (1e16 + 1.0 == 1e16));
        System.out.println("floatULP(2^24)=" + Math.ulp(0x1.0p24f));
        System.out.println("nextUpMaxInfinity=" + Double.isInfinite(Math.nextUp(Double.MAX_VALUE)));
        System.out.println("ulpMaxFinite=" + Double.isFinite(Math.ulp(Double.MAX_VALUE)));
        System.out.println("ulpInfinityInfinite=" + Double.isInfinite(Math.ulp(Double.POSITIVE_INFINITY)));
        System.out.println("ulpNaNisNaN=" + Double.isNaN(Math.ulp(Double.NaN)));
        System.out.println("nextUpNegZeroMinPositive=" + (Math.nextUp(-0.0) == Double.MIN_VALUE));
        System.out.println("nextAfterOneDown=" + (Math.nextAfter(1.0, 0.0) == below));
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 UlpSpacingDemo.java
java UlpSpacingDemo
```

Exact stdout:

```text
ulp(1.0)=2.220446049250313E-16
nextUp(1.0)=1.0000000000000002
nextDown(1.0)=0.9999999999999999
gapAbove=2.220446049250313E-16
gapBelow=1.1102230246251565E-16
upperGapEqualsUlp=true
lowerGapEqualsUlp=false
ulpHex=0x1.0p-52
floatUlpHex=0x1.0p-23
ulp(0.0)==MIN_VALUE=true
ulp(minNormal)==MIN_VALUE=true
ulp(2.0)/ulp(1.0)=2.0
ulp(2^53)=2.0
2^53PlusOneLost=true
ulp(1e16)=2.0
1e16PlusOneLost=true
floatULP(2^24)=2.0
nextUpMaxInfinity=true
ulpMaxFinite=true
ulpInfinityInfinite=true
ulpNaNisNaN=true
nextUpNegZeroMinPositive=true
nextAfterOneDown=true
```

These lines illustrate four aspects:

1. **Asymmetry right at `1.0`**: `upperGapEqualsUlp=true`, `lowerGapEqualsUlp=false`; ULP at `1.0` is `2^-52` while the step down is `2^-53`.
2. **Magnitude governs spacing**: `ulp(2.0)/ulp(1.0)=2.0`; at `2^53` and `1e16`, a single step has magnitude `2.0`.
3. **Zero and subnormal**: `Math.ulp(0.0) == Double.MIN_VALUE`, `Math.ulp(Double.MIN_NORMAL) == Double.MIN_VALUE`.
4. **Boundary exceptions**: `nextUp(Double.MAX_VALUE)` moves to Infinity even though ULP at max remains finite; `NaN` and Infinity follow special ULP rules.

The example uses `Double.toHexString` and `Float.toHexString` to display exact binary exponents, preventing short decimal display strings from making you think atomic spacings are all representable with the same number of decimal digits.

## 10. Is ULP the Computation Error?

**They are not the same.** ULP is the resolution of the representable value set near a number, whereas **error** is the distance between the approximated result and the mathematical result or chosen reference value.

For example, `Math.ulp(1.0)` is about `2.22E-16`, yet that **does not mean** every `double` calculation will err by at most `2.22E-16`. Actual error depends on value magnitudes, rounding behavior, number of calculation steps, problem conditioning, and algorithm stability. Subtracting two very close numbers can lose many significant digits due to **catastrophic cancellation**; iterating millions of operations can accumulate error.

When a basic operation rounds properly to the nearest `double` in an appropriate range, rounding error can be analyzed in fractions of one ULP **of the ideal result**. However, claims like “every algorithm errs by at most half a ULP” are **false**. The error across a chain of operations can exceed many ULPs, especially with sensitive data or near cancellation.

Furthermore, **the ULP unit at `a` and at `b` can differ** when the two numbers belong to different exponent scales. When reporting “off by 2 ULPs,” define the convention of which point's ULP or bit-pattern ordering is used, and how sign/zero/infinity are handled.

## 11. Using `Math.ulp` to Compare Floating-Point Numbers: Know the Limits

Some code snippets attempt approximate comparison:

```java
double a = 1.0;
double b = Math.nextUp(a);
boolean near = Math.abs(a - b) <= Math.ulp(a); // true in this case
```

That is a **controlled example**, not a “universally correct double comparison function for all inputs.” Several problems arise if you treat `Math.ulp(a)` as a fixed threshold:

- At `2^e` boundaries, the upward step and downward step differ.
- Comparing two numbers widely separated in magnitude requires an explicit policy on relative/absolute tolerances; a ULP at one endpoint alone does not capture the full picture.
- `a - b` can overflow to Infinity or underflow to zero in boundary cases.
- `NaN`, Infinity, and signed zero require explicit business rules; `NaN == NaN` is always `false`, while both zeros compare `true` with `==`.
- Being “within a few ULPs” only means they are close on the **representation grid**, not that they are accurate relative to reality.

If testing a numerical algorithm, you can use **absolute error** `abs(a-b)`, **relative error** scaled by magnitude, or ULP distance under a clear definition, depending on the measurement and data. Near zero, pure relative tolerance is often awkward; at very large magnitudes, a fixed absolute tolerance can be too strict.

For **currency** or decimal numbers that must obey accounting precision rules, prefer `BigDecimal` created from decimal strings (`new BigDecimal("0.1")`) with an explicit rounding mode; do not treat ULP as a substitute for decimal exactness.

## 12. Common Misconceptions

| Misconception | Reality | How to Verify |
| --- | --- | --- |
| “`double` has ~15–16 digits of precision so all steps are equally small” | Absolute step size grows as the exponent grows | `Math.ulp(x)` at multiple magnitudes |
| `Math.ulp(x) == Math.nextUp(x)-x == x-Math.nextDown(x)` everywhere | False at power-of-2 boundaries such as `1.0` | Print both steps |
| `Math.ulp(0.0) == 0.0` | ULP at zero equals the smallest positive subnormal | `Math.ulp(0.0) == Double.MIN_VALUE` |
| `Double.MIN_VALUE` is the smallest negative number | It is the smallest nonzero **positive** number | Distinguish `Double.MIN_VALUE` and `-Double.MAX_VALUE` |
| `2^53 + 1` always differs from `2^53` in `double` | Cannot represent every consecutive integer past the threshold | `0x1.0p53 + 1.0 == 0x1.0p53` |
| ULP is the maximum error of any program | ULP describes grid spacing, not an algorithmic guarantee | Analyze error per specific calculation |
| `Math.ulp(Double.MAX_VALUE)` must be Infinity | ULP at MAX is still finite, while `nextUp(MAX)` is Infinity | Compare the two separate calls |
| Comparing `double` only needs a `1e-9` tolerance at all scales | A fixed threshold does not suit all ranges | Define absolute/relative error per requirements |
| `float` and `double` have the same ULP at `1.0` | They have 24 and 53 effective significand bits | Compare `Math.ulp(1f)` and `Math.ulp(1d)` |

## 13. Self-Check Questions

1. **What does ULP describe?** The representation resolution/spacing associated with the least-significant bit position of the significand near a floating-point value, not the error of arbitrary algorithms.
2. **What is `Math.ulp(1.0)`?** `2^-52` = about `2.220446049250313E-16`. For `float 1.0f`, ULP is `2^-23`.
3. **Why is `1.0-Math.nextDown(1.0)` only half of `Math.ulp(1.0)`?** Because `1.0` is the boundary between two consecutive exponent regions; the downward step is smaller than the upward step.
4. **How does `Math.ulp(2.0)` compare to `Math.ulp(1.0)`?** Twice as large; they are `2^-51` and `2^-52`, respectively.
5. **At `2^53`, does adding `1.0` to a `double` necessarily change the number?** No; `2^53+1` lies halfway between two representable values and rounds to `2^53`.
6. **Does `Math.ulp(0.0)` equal 0?** No; it equals `Double.MIN_VALUE`, the smallest positive subnormal step.
7. **Is `Math.ulp(Double.MAX_VALUE)` Infinity?** No, it remains finite; specifically `Math.nextUp(Double.MAX_VALUE)` returns Infinity.
8. **Which API finds the representable number immediately below `x`?** `Math.nextDown(x)`; do not assume `x - Math.ulp(x)` is always accurate.
9. **Can `Math.ulp` directly replace `BigDecimal` for exact monetary calculations?** No; decimal exactness and currency rounding rules are separate concerns.

**Conclusion:** ULP explains why floating-point numbers **have gaps** and why absolute spacing **varies with magnitude and exponent**. In Java, use `Math.ulp` alongside `Math.nextUp`/`nextDown` to inspect the representation grid, paying attention to power-of-2 boundaries, the subnormal range, and special values. In practical computation, clearly separate **representation resolution** from **algorithmic error** and choose comparison/rounding strategies according to business requirements.