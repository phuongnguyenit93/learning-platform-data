# Comparing with Absolute Tolerance in Java

When working with `float` and `double`, two values representing the same mathematical result do not always share the same **bit pattern**. For instance, adding `0.1 + 0.2` in `double` usually produces a value printed as `0.30000000000000004`, which differs from the literal `0.3`. When a measurement problem permits a small discrepancy, we can compare using **absolute tolerance** instead of requiring `==`.

```java
double actual = 0.1 + 0.2;
double expected = 0.3;
double epsilon = 1e-12;

boolean exact = actual == expected; // false
boolean close = Math.abs(actual - expected) <= epsilon; // true
```

However, the second expression **is not a universal replacement for `==`**. It is meaningful only when `epsilon` is chosen from actual requirements, data units, and with an explicit policy for NaN, infinity, very large numbers, and numbers near 0. This lesson presents absolute tolerance comparison, its engineering meaning, a Java 17+ implementation, testing strategies, and boundaries where it should not be misused.

## 1. Why Does Comparing `double` with `==` Often Surprise Developers?

`double` stores numbers in IEEE 754 binary64 format with a 53-bit significand. Fractions such as `0.1` and `0.2` have no finite binary representation, so Java stores the **closest representable** values. Addition then applies floating-point rounding rules.

```java
double sum = 0.1 + 0.2;
System.out.println(sum);        // 0.30000000000000004
System.out.println(sum == 0.3); // false
```

There is no bug where "Java adds incorrectly" here. The issue is that the operation runs on approximate binary values; the result is close to 0.3 but does not have the exact same binary64 value as the literal `0.3`.

**Distinguish two types of requirements:**

- **Exact equality:** Two numeric values truly need to be equal under Java semantics; `==` can be the right choice, such as checking integer counters, identifiers, or a numeric state that must match exactly.
- **Closeness within a tolerance:** Two measurements or calculation results can differ slightly and still satisfy application requirements. In that case, a specific error threshold may be more suitable.

Do not turn every floating-point comparison into an approximate one out of habit. Approximation is a **business policy**, not a default property of every `double`.

## 2. Definition of Absolute Error

For two finite values `a` and `b`, the **absolute error** is:

\[
E_{\mathrm{abs}} = |a-b|
\]

We say two values are **close within an absolute tolerance** `ε` when:

\[
|a-b| \leq \varepsilon
\qquad (\varepsilon \geq 0)
\]

In Java, the corresponding expression allows a simple check:

```java
boolean close = Math.abs(a - b) <= epsilon;
```

Here `Math.abs(double)` returns the non-negative magnitude of the difference (except in special cases like NaN), and `<=` adopts the convention of **allowing equality at the threshold**. If the problem requires strictly less than (`<`), use `<`, while clearly documenting the test contract.

### Numerical Example

Given `a = 12.34`, `b = 12.35`, and allowed tolerance `epsilon = 0.02`:

```text
absolute error = |12.34 - 12.35|
               ≈ 0.01
tolerance      = 0.02
0.01 <= 0.02   => true
```

Decimal literals entered as `double` may be rounded; the `≈` symbol reminds us that the actual subtraction also uses binary numbers. This example only illustrates the **magnitude of the difference**; conclusions should be verified with the actual data and numeric types.

With values **exactly representable in binary**, the boundary is crisp:

```java
System.out.println(Math.abs(1.0 - 1.125) <= 0.125); // true
System.out.println(Math.abs(1.0 - 1.25) <= 0.125);  // false
```

`1.125`, `1.25`, and `0.125` are fractions whose denominators are powers of 2, so there is no ambiguity from literal storage here.

## 3. `epsilon` Is a Threshold with **Units**, Not a Magic Constant

`epsilon` must express the **largest difference acceptable to the problem**.

| Data | Example absolute tolerance | Units and meaning |
| --- | --- | --- |
| Temperature sensor | `0.2` | 0.2 °C if data represents °C |
| Coordinates in meters | `0.005` | 5 mm |
| Time in seconds | `0.001` | 1 ms |
| Voltage | `0.01` | 0.01 V |
| Algorithm checking rounding error around 0.3 | `1e-12`, only when justified | A choice for a test problem, **not a standard threshold** for all `double`s |

These illustrative numbers are not measurement recommendations for a specific device; device specifications and application contracts determine the real threshold.

If `a` and `b` are in **meters**, `epsilon` must also be in **meters**. If one side uses meters and the other uses millimeters, the comparison can look "syntactically valid" while being **semantically wrong**.

**Do not reuse a single `1e-6` across every project** just because it looks small. In a system measuring nanometers, `1e-6` can be way too large; when measuring distances in millions of kilometers, it can be way too small.

### Why Is `Double.MIN_VALUE` Not a Default Epsilon?

`Double.MIN_VALUE` is the **smallest positive non-zero** number representable in binary64, approximately `4.9e-324`. It does not represent typical rounding error. `Math.ulp(1.0)` is about `2.220446049250313e-16` near 1.0; the spacing between representable values changes with magnitude. Using `Double.MIN_VALUE` to check "closeness" is usually equivalent to requiring nearly exact equality.

Even a fixed multiple of `Math.ulp(1.0)` does not make sense for every value: floating-point quantization step depends on the number's magnitude, whereas an absolute tolerance is a difference **in business units**.

## 4. Java 17+ Comparison Function with Input Validation

The expression `Math.abs(a-b) <= epsilon` is concise, but **does not state a policy for NaN, infinity, or invalid thresholds**. For measurement data requiring **finite** numbers, you can write:

```java
static boolean closeAbs(double a, double b, double epsilon) {
    if (!Double.isFinite(epsilon) || epsilon < 0.0) {
        throw new IllegalArgumentException(
                "epsilon must be finite and >= 0");
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }
    if (a == b) {
        return true;
    }
    return Math.abs(a - b) <= epsilon;
}
```

This is an **illustrative method**, which must be placed inside a class. A complete runnable version is in Section 10.

**Function contract:**

1. `epsilon` must be **finite** and **non-negative**. NaN, ±Infinity, and negative epsilon are rejected with `IllegalArgumentException`.
2. If `a` or `b` is NaN/infinity, return `false`. This fits problems that accept only **finite measured values**.
3. Two finite numbers that are already equal under `==` are considered close, even when epsilon is 0.
4. For remaining finite numbers, return the result of `Math.abs(a-b) <= epsilon`.

Do not treat this policy as the **only valid rule**. An application might regard `+Infinity` and `+Infinity` as the same special state, or require zero to distinguish signs. If so, **define a different policy explicitly**, rather than changing code without explanation.

### Why Validate `epsilon` First?

If `epsilon = Double.NaN`, comparing `<=` with NaN is always false; if `epsilon = Double.POSITIVE_INFINITY`, wildly different pairs of numbers would be considered close, rendering the check meaningless. If `epsilon < 0`, even two identical finite numbers fail the ordinary threshold formula.

Throwing `IllegalArgumentException` exposes configuration mistakes or bad threshold choices right at the call boundary.

### Is the `a == b` Branch Necessary?

In this function, for finite numbers, that branch makes clear that **exact equality must be accepted even when epsilon is 0**. The subtraction and absolute-value formula also produces the right result in that case; the branch merely makes the contract easier to read and avoids unnecessary subtraction.

Do **not** place `a == b` before the finiteness check if your policy requires rejecting Infinity: `Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY` is `true`, yet the application may not want to treat two infinite measurements as valid.

## 5. Edge Cases That Must Be Handled Explicitly

### 5.1. NaN

`Double.NaN` typically represents an undefined result in floating-point arithmetic. Comparison operators behave specially with NaN:

```java
double x = Double.NaN;
System.out.println(x == x); // false
System.out.println(Math.abs(x - 1.0) <= 1.0); // false
```

The `closeAbs` function above returns `false` for NaN before subtracting. If you want two NaN values to count as the same **missing-data state**, use separate logic; do not conflate "same state" with **numerical error**.

### 5.2. Infinity

`Math.abs(Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY)` is NaN, so a pure threshold check returns `false`. Yet `Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY` is `true`. Two simple checks have different policies.

Therefore, the clear approach is to **decide upfront** whether non-finite values are permitted. For measurements that must be finite, `Double.isFinite` explicitly excludes infinity and NaN.

### 5.3. Signed Zero

`+0.0` and `-0.0` are considered equal under `==`:

```java
System.out.println(+0.0 == -0.0); // true
```

The absolute-tolerance comparison function above returns `true` for this pair, even with `epsilon = 0`. If you need to compare **IEEE 754 bit patterns** (such as serialization or special numerical protocols), `+0.0` and `-0.0` differ; in that case, arithmetic proximity **is not the right problem**. Consider `Double.doubleToRawLongBits` with an explicit NaN policy.

### 5.4. Difference Overflow When Subtracting Two Very Large Finite Numbers

Two `double`s can both be finite while their difference exceeds the `double` range:

```java
double a = Double.MAX_VALUE;
double b = -Double.MAX_VALUE;
double difference = a - b; // +Infinity
```

If `epsilon` is also a finite number, the mathematical difference of the pair above exceeds every representable finite epsilon. Thus returning `false` makes sense. This case shows that **subtraction also has a representation range**, and you should not blindly apply algebraically equivalent transformations in floating-point code.

### 5.5. Values Very Close to 0

Suppose `a = 1e-12`, `b = 0`, and `epsilon = 1e-9`. The two values are considered close because `1e-12 <= 1e-9`, yet `a` is still **a non-zero value**.

An absolute threshold determines "close enough to zero" in the chosen units, but **does not turn that value into mathematical zero**. If `a` is a leakage current that must be detected, or an important tiny physical signal, treating near-zero as zero can hide a real event.

## 6. When Is Absolute Error Strong, and When Is It Weak?

### Strong: Quantities with a Fixed Domain and Difference Threshold

For example, checking a measured temperature against a target temperature with an allowed error of ±0.2 °C gives an absolute threshold a clear meaning. With coordinates measured in meters, checking that the difference is at most 1 mm is also a decision grounded in **units**.

Absolute error is especially intuitive near zero: "how many units away from zero is this value?"

### Weak: Data Spanning Many Orders of Magnitude

Consider two cases using the same `epsilon = 1e-6`:

- Comparing values around `1e-12`: the threshold is many times larger than the values, easily treating proportionally very different numbers as equivalent.
- Comparing values around `1e12`: the threshold is smaller than the spacing between some adjacent `double` pairs in this range, which can be overly strict.

Therefore, if acceptable error **depends on ratio or magnitude**, a **relative** tolerance or a combined relative/absolute tolerance may be more appropriate. However, that is a different policy; choose it only after specifying outputs and business error bounds.

A commonly used combined formula is:

\[
|a-b| \leq \max(\varepsilon_{\mathrm{abs}},\ \varepsilon_{\mathrm{rel}}\max(|a|,|b|)).
\]

Do not use that formula while forgetting to check for NaN, Infinity, negative thresholds, or overflow when computing intermediate quantities. Here the focus is **absolute tolerance**; the combined formula only situates the method's limits.

### Selection Table

| Scenario | Is absolute tolerance suitable? | Notes |
| --- | --- | --- |
| Values near 0 with clear units and threshold | Usually suitable | E.g., absolute distance to 0 |
| Sensor deviation allowed up to 0.2 units | Suitable if specified by contract | Threshold must have the same unit |
| Comparing values from `1e-12` to `1e12` | A single threshold is usually insufficient | Consider relative/combined tolerance |
| Checking integers, IDs, or hashes | Do not use | Use exact equality and integer types |
| Currency needing exactness to the cent | Unsuitable as a workaround for error | `BigDecimal` or smallest-unit integers |
| Comparing bit patterns and signed zero | Unsuitable | Use bit-inspection APIs |
| NaN, Infinity in state models | Only with an explicit policy | Do not call them "close" measurements |
| Using a threshold to mask an algorithmic bug | Unsuitable | Investigate the root cause of error |

## 7. `float`, `double`, and Data Type Effects

`float` has roughly 24 bits of significand precision, while `double` has 53 bits. Thus, the same mathematical value can incur different storage errors depending on the type.

```java
float x = 0.1f;
double y = 0.1d;

System.out.println((double) x); // 0.10000000149011612
System.out.println(y);          // 0.1
```

When comparing a `float` with a `double`, the `float` value is **widened to `double` without restoring lost information**. If you use a method taking `double`, widening is valid; however, the threshold must be chosen based on the actual resolution of the binary32 input, without assuming both operands have the same precision.

### Why Not Use One Invariant Epsilon for Every `float`?

Like `double`, the spacing between two representable `float` values **grows with magnitude**. Near 1.0, `Math.ulp(1.0f)` is about `1.1920929e-7`; near 1.0 for `double`, `Math.ulp(1.0d)` is about `2.220446049250313e-16`.

`Math.ulp` measures representation step size in a value region, **not an auto-generated business error threshold**. It is helpful when assessing whether an absolute threshold is smaller than the data's resolution.

If data comes from a sensor accurate to 0.01 units, a threshold of `1e-12` may be completely unrealistic, even if the storage type is `double`.

## 8. "Nearly Equal" Comparison Is Not Mathematical Equality

With `epsilon > 0`, an approximate comparison can be:

- **Symmetric:** `closeAbs(a,b,epsilon)` and `closeAbs(b,a,epsilon)` give the same result on finite numbers under the absolute tolerance criterion.
- **Reflexive on finite values:** every **finite** value is close to itself if epsilon is valid and non-negative.
- **Not transitive:** `a` close to `b` and `b` close to `c` **does not guarantee** `a` is close to `c`.

Example choosing exactly representable numbers:

```java
double epsilon = 0.25;
double a = 0.0;
double b = 0.25;
double c = 0.5;

// closeAbs(a,b,epsilon) == true.
// closeAbs(b,c,epsilon) == true.
// closeAbs(a,c,epsilon) == false.
```

Therefore, do **not** use epsilon comparison in place of `equals`/`hashCode` for keys in `HashMap`/`HashSet`, or expect it to behave as an equivalence relation for grouping objects. Sorting algorithms and data structures require consistent contracts; an epsilon comparator lacking transitivity can violate the comparison contract.

### Another Consequence: "Nearly Equal" Can Blur Bounds

If you use `closeAbs(x, limit, epsilon)` to decide "`x` must not exceed `limit`," that is not a proper inequality check: a number **far below** the limit is valid yet not "close" to the limit. **Bound-checking** problems should use an inequality with an explicit boundary policy:

```java
boolean withinUpperBound = x <= upperBound;
```

If slight overshoot is permitted, explicitly specify "`x <= upperBound + tolerance`" along with overflow protection and non-finite handling, rather than vaguely calling it "nearly equal." Approximate comparison only answers **the difference between two numbers**, not ordering logic.

## 9. Notes on Writing Automated Tests

In unit tests, there are usually three key inputs: **actual**, **expected**, and **tolerance**.

```java
double actual = 0.1 + 0.2;
double expected = 0.3;
double tolerance = 1e-12;

if (Math.abs(actual - expected) > tolerance) {
    throw new AssertionError("Actual is too far from expected");
}
```

This snippet illustrates the idea, though it lacks a full NaN/Infinity policy: for NaN, `>` also returns `false`, causing the throw branch **not to execute**. Therefore, when writing a reliable test helper, rely on the result of a function that already checks finiteness and the threshold:

```java
if (!closeAbs(actual, expected, tolerance)) {
    throw new AssertionError("Values differ beyond absolute tolerance");
}
```

With a testing library like JUnit, use the floating-point assertion overload with `delta` if your version/framework provides it, and read that API's contract (especially for NaN and Infinity). Do not assume every library handles special values identically to a custom helper.

### Test Cases to Include

| Case | Example | Expected per `closeAbs` helper |
| --- | --- | --- |
| Small difference within threshold | `0.1+0.2`, `0.3`, `1e-12` | `true` |
| Difference exceeding threshold | Same pair with `1e-17` | `false` |
| Exact boundary | `1.0`, `1.125`, `0.125` | `true` |
| Outside boundary | `1.0`, `1.25`, `0.125` | `false` |
| Equal finite values | `2.0`, `2.0`, `0` | `true` |
| Opposite-signed zeros | `+0.0`, `-0.0`, `0` | `true` |
| With NaN | `NaN`, `NaN`, `1` | `false` |
| Infinity | `+Infinity`, `+Infinity`, `1` | `false` |
| Negative epsilon | `1`, `1`, `-1` | `IllegalArgumentException` |
| NaN/infinite epsilon | `1`, `1`, `NaN` | `IllegalArgumentException` |
| Two finite numbers whose difference overflows | `MAX_VALUE`, `-MAX_VALUE`, `MAX_VALUE` | `false` |

Also test **unit changes** and **upper/lower measurement bounds**, because a threshold that makes sense for small data may be too loose or too tight in a large domain.

## 10. Standalone Runnable Java 17+ Program

Create the file `AbsoluteToleranceDemo.java`:

```java
import java.util.Locale;

public class AbsoluteToleranceDemo {
    static boolean closeAbs(double a, double b, double epsilon) {
        if (!Double.isFinite(epsilon) || epsilon < 0.0) {
            throw new IllegalArgumentException(
                    "epsilon must be finite and >= 0");
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }
        if (a == b) {
            return true;
        }
        return Math.abs(a - b) <= epsilon;
    }

    public static void main(String[] args) {
        double sum = 0.1 + 0.2;
        System.out.printf(Locale.ROOT, "0.1 + 0.2 = %.17f%n", sum);

        System.out.println("Exact equality with 0.3: " + (sum == 0.3));
        System.out.println("epsilon 1e-12: " + closeAbs(sum, 0.3, 1e-12));
        System.out.println("epsilon 1e-17: " + closeAbs(sum, 0.3, 1e-17));

        System.out.println("At boundary: "
                + closeAbs(1.0, 1.125, 0.125));
        System.out.println("Outside boundary: "
                + closeAbs(1.0, 1.25, 0.125));

        System.out.println("Signed zero: "
                + closeAbs(+0.0, -0.0, 0.0));
        System.out.println("NaN accepted: "
                + closeAbs(Double.NaN, Double.NaN, 1.0));
        System.out.println("Infinity accepted: "
                + closeAbs(Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, 1.0));

        System.out.println("Large values: "
                + closeAbs(1e12, 1e12 + 0.01, 0.001));
        System.out.println("Tiny signal considered close: "
                + closeAbs(1e-12, 0.0, 1e-9));
        System.out.println("Gap overflow accepted: "
                + closeAbs(Double.MAX_VALUE,
                        -Double.MAX_VALUE, Double.MAX_VALUE));

        try {
            closeAbs(1.0, 1.0, Double.NaN);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid tolerance: rejected");
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 AbsoluteToleranceDemo.java
java AbsoluteToleranceDemo
```

Stdout (verified):

```text
0.1 + 0.2 = 0.30000000000000004
Exact equality with 0.3: false
epsilon 1e-12: true
epsilon 1e-17: false
At boundary: true
Outside boundary: false
Signed zero: true
NaN accepted: false
Infinity accepted: false
Large values: false
Tiny signal considered close: true
Gap overflow accepted: false
Invalid tolerance: rejected
```

The most important takeaway from the example is that **the same pair of values** can be close under one epsilon and not close under a smaller epsilon. That is not a contradiction: epsilon is an **input defining the contract**, not an intrinsic constant of `double`.

The line `Tiny signal considered close: true` is also a warning: an overly wide absolute threshold can mask small signals. The line `Infinity accepted: false` reflects the helper's **finite-numbers-only policy**, not Java's `==` operator.

## 11. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| `a == b` for all floating-point calculation results | Rounding steps can cause bit differences | Use absolute tolerance only when business logic permits |
| Using a fixed `1e-6` epsilon for all units and domains | Threshold is too large or too small depending on context | Choose epsilon by unit, domain, resolution, and requirements |
| Using `Double.MIN_VALUE` as a "default error" | It is the smallest positive subnormal number | Choose threshold per problem, understand `Math.ulp` |
| Using negative or NaN epsilon | Approximate formula loses meaning or gives unexpected results | Validate epsilon is finite and non-negative |
| Checking only `if (abs(actual-expected) > eps) fail` | With NaN, `>` returns false and can miss errors | Use `if (!closeAbs(...)) fail` with a NaN policy |
| Treating Infinity == Infinity as "close" when measurements must be finite | `==` and error comparison have different contracts | Check `Double.isFinite` |
| Requiring `+0.0` and `-0.0` to differ in measurements | The sign of 0 usually has no distance meaning | Compare by proximity; use raw bits when sign distinction is needed |
| Using tolerance to compare indices/IDs | Mistakenly accepts two distinct values | Use integer types and appropriate `==`/`equals` |
| Using `closeAbs` as `equals`/Comparator | Closeness is not transitive | Separate approximate checks from collection contracts |
| Forgetting unit conversions | A 0.01 m threshold is not 0.01 mm | Normalize units before comparing |
| Thinking only about literal-storage error | Every intermediate operation can round | Examine the entire computation pipeline |
| Using `float` and picking a `double` epsilon without evaluation | `float` has lower resolution | Check `Math.ulp` and source data error level |
| Using "close to limit" instead of checking `<=` | Closeness does not express the allowed domain | Write explicit bound conditions and boundary policies |

## 12. Self-Check Questions

1. Why is `0.1 + 0.2 == 0.3` `false` in Java? When does switching to absolute comparison make sense?
2. Given `a = 1.0`, `b = 1.125`, and `epsilon = 0.125`, what does `Math.abs(a-b) <= epsilon` return? What if `<` is used instead of `<=`?
3. Why must epsilon have the **same unit** as the data? What happens if one value is in meters and another is in millimeters?
4. If a sensor measures near zero but a `1e-12` signal is significant, why can an epsilon of `1e-9` be dangerous?
5. Why is `Double.MIN_VALUE` not an appropriate threshold for checking operations near 1.0?
6. What does `Math.abs(Double.NaN - expected) <= epsilon` return? What issue can arise when using `Math.abs(...) > epsilon` to fail a unit test?
7. How does `closeAbs` in this lesson handle Infinity? If an application wants to treat same-sign Infinity as the same state, how would you change the contract?
8. What does `closeAbs(+0.0,-0.0,0.0)` return? When should you inspect bits instead of arithmetic proximity?
9. Why is the "nearly equal" relation not transitive? Give an example of three numbers where adjacent pairs are close but the two ends are not.
10. When data spans from `1e-12` to `1e12`, why might a single fixed absolute epsilon be unsuitable?
11. If sensor data is stored as `float` and then compared with `double` data, does widening restore the lost bits?
12. Why does `closeAbs(x,upperBound,eps)` not directly replace `x <= upperBound` when checking that a value does not exceed a threshold?

## 13. References

- [Java SE 17 — `Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): NaN/Infinity values, `isFinite`, `isNaN`, and rules related to binary64.
- [Java SE 17 — `Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `abs(double)`, `ulp(double)`, and arithmetic operations.
- [Java Language Specification, `4.2.3 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): floating-point formats and special values.
- [Java Language Specification, `15.21.1 — Numerical Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21.1): `==`/`!=` and behavior with NaN/signed zero.

**Remember:** Comparing with absolute tolerance is the rule **`|a-b| <= epsilon`**, where `epsilon` must be chosen according to **units, domain, and the accuracy requirements of the problem**. It is a deliberate way to evaluate discrepancy, **not a universal replacement for `==`**. To implement it reliably in Java, define policies for NaN/Infinity/±0, validate epsilon, write boundary tests, and know when a relative tolerance or a different numeric model is more appropriate.
