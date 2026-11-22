# `exp`, `log`, `log10`, `expm1`, and `log1p` in Java

Java provides five common exponential/logarithmic functions in `java.lang.Math` and `java.lang.StrictMath`. They are closely related mathematically, but **cannot be substituted mechanically** in floating-point calculations:

- `Math.exp(x)` computes \(e^x\).
- `Math.log(x)` computes \(\ln(x)\), the natural logarithm base \(e\).
- `Math.log10(x)` computes \(\log_{10}(x)\), the base-10 logarithm.
- `Math.expm1(x)` computes \(e^x-1\) **directly with better precision** when \(x\) is very close to 0.
- `Math.log1p(x)` computes \(\ln(1+x)\) **directly with better precision** when \(x\) is very close to 0.

All five take one `double` parameter and return `double`. If an `int` or `float` is passed, Java widens it to `double` before the call. These functions do not return arbitrary-precision exact integer values; they operate within the IEEE 754 limits of `double`.

**Learning goal:** choose the right function, understand the domain and `NaN`/`Infinity`/`-0.0` cases, avoid precision loss from writing `exp(x)-1` or `log(1+x)` manually, and know when `StrictMath` is needed instead of `Math`.

## 1. Overview Table and Mathematical Relationships

| Java API | Mathematical Expression | Condition for Ordinary Finite Real Result | Memorable Case |
| --- | --- | --- | --- |
| `Math.exp(x)` | \(e^x\) | \(x\) finite and does not overflow/underflow output range | `exp(0.0) = 1.0` |
| `Math.log(x)` | \(\ln(x)\) | \(x > 0\), finite | `log(1.0) = 0.0` |
| `Math.log10(x)` | \(\log_{10}(x)\) | \(x > 0\), finite | `log10(1000.0) = 3.0` |
| `Math.expm1(x)` | \(e^x - 1\) | \(x\) finite, result within range | `expm1(0.0) = 0.0` |
| `Math.log1p(x)` | \(\ln(1+x)\) | \(x > -1\), finite | `log1p(0.0) = 0.0` |

The finiteness conditions listed in the table describe scenarios that **normally yield a finite result**; `exp` and `expm1` can still overflow or underflow even when the `double` argument is finite. `log`, `log10`, and `log1p` also define how to handle inputs at **domain boundaries**, rather than simply throwing exceptions like integer arithmetic.

The base \(e\) is approximately `2.718281828459045`, available as the constant `Math.E`:

```java
System.out.println(Math.E);                  // 2.718281828459045
System.out.println(Math.exp(0.0));           // 1.0
System.out.println(Math.log(1.0));           // 0.0
System.out.println(Math.log10(1000.0));      // 3.0
```

Use familiar numerical examples to grasp the meaning, but **do not assume every function composition will be completely exact** since most calculations round to `double`.

## 2. `Math.exp(x)`: Base-`e` Exponential Function

`Math.exp(x)` computes \(e^x\); the mathematical result is always **positive** for any finite real \(x\). Properties:

- `Math.exp(0.0)` and `Math.exp(-0.0)` both equal `1.0`.
- `Math.exp(1.0)` approximates \(e\).
- `Math.exp(Math.log(a))` approximates `a` when `a > 0` and no rounding/domain limits are hit.
- `Math.exp(x + y)` corresponds to \(e^x e^y\) mathematically, but the two computations in `double` **can differ due to rounding error or overflow**.

```java
double rate = 0.05;
double years = 10.0;
double growthFactor = Math.exp(rate * years); // e^0.5, growth factor
```

This is an illustrative snippet inside a method, not a standalone Java program. The \(e^{rt}\) model is commonly used for continuous growth; the application must clearly define the time unit and the meaning of `rate`.

### Overflow and Underflow of `exp`

`double` cannot hold all values of \(e^x\). Example:

```java
System.out.println(Math.exp(800.0));  // Infinity
System.out.println(Math.exp(-800.0)); // 0.0
```

`Math.exp(800.0)` exceeds the finite magnitude of `double`, yielding positive infinity. `Math.exp(-800.0)` is mathematically positive but too small to represent, so it rounds to positive zero.

Therefore, **`Math.exp(x) == 0.0` does not necessarily mean \(e^x=0\) mathematically**. For extremely small probability calculations, log-likelihoods, or data spanning many orders of magnitude, you should sometimes keep data in the **logarithmic domain** instead of exponentiating too early.

## 3. `Math.log(x)`: Natural Logarithm

`Math.log(x)` computes \(\ln(x)\), the inverse of \(e^x\) over the positive real domain:

```java
double x = 3.0;
double logX = Math.log(x);
double approximatelyOriginal = Math.exp(logX);
```

Due to rounding, `approximatelyOriginal` is not guaranteed to be bit-identical to `x`. You should not write tests asserting `Math.exp(Math.log(x)) == x` for every `double`.

Some rules:

- `Math.log(1.0)` returns `0.0`.
- If `0 < x < 1`, \(\ln(x)\) is negative.
- If `x > 1`, \(\ln(x)\) is positive.
- `Math.log(+0.0)` and `Math.log(-0.0)` both return `-Infinity`.
- `Math.log(x)` with `x < 0` returns `NaN`, because there is no real logarithm.
- `Math.log(Double.POSITIVE_INFINITY)` returns `Infinity`.

```java
System.out.println(Math.log(1.0));           // 0.0
System.out.println(Math.log(0.0));           // -Infinity
System.out.println(Math.log(-1.0));          // NaN
System.out.println(Math.log(Double.POSITIVE_INFINITY)); // Infinity
```

**Does not throw `ArithmeticException` for typical out-of-domain inputs.** This is a floating-point function; the application needs to check the result or input if NaN/infinity is not allowed.

Logarithms also turn products into sums mathematically: \(\ln(ab)=\ln(a)+\ln(b)\) for \(a,b>0\). This is useful when the product of many positive values is too large or too small, though rounding errors when taking logs and converting back must be considered.

## 4. `Math.log10(x)`: Base-10 Logarithm

`Math.log10(x)` returns \(\log_{10}(x)\). It shares the same positive real domain as `log`, but with a **different base**:

```java
System.out.println(Math.log10(1.0));    // 0.0
System.out.println(Math.log10(10.0));   // 1.0
System.out.println(Math.log10(1000.0)); // 3.0
```

Use `log10` when the problem involves decimal orders of magnitude, base-10 scales, or ratios in powers of 10. Use `log` when the formula requires the natural logarithm, such as continuous processes, calculus, and many probability models.

Mathematical relationship:

\[
\log_{10}(x)=\frac{\ln(x)}{\ln(10)}.
\]

Do not unnecessarily implement `Math.log(x) / Math.log(10.0)` instead of `Math.log10(x)`: Java already has a direct API, and different floating-point calculations can differ in the last digit.

**General change of base:** \(\log_b(x)=\ln(x)/\ln(b)\), with `x > 0`, `b > 0`, and `b != 1`:

```java
double base = 2.0;
double value = 8.0;
double logBase2 = Math.log(value) / Math.log(base);
```

This is the formula for computing base-2 logarithm from two `log` calls; the result is an approximation. When `base` is extremely close to 1, the denominator \(\ln(base)\) is small so the problem can be sensitive to error; evaluate stability rather than just substituting a division.

## 5. Why Can `Math.exp(x) - 1.0` Lose Precision?

For \(x\) near 0, \(e^x\) is near 1. If you call `Math.exp(x)`, the result is rounded to the `double` grid around 1. Subtracting 1 afterward can **lose the entire tiny signal**.

Consider:

```java
double x = 1e-16;
double naive = Math.exp(x) - 1.0;
double stable = Math.expm1(x);

System.out.println(naive);  // 0.0
System.out.println(stable); // 1.0E-16
```

Mathematically, \(e^{10^{-16}}-1\) is approximately \(10^{-16}\), but `Math.exp(1e-16)` rounds to `1.0` at `double` precision, making `1.0-1.0` equal to 0. This is **cancellation** (loss of information when subtracting two nearly equal numbers).

`Math.expm1(x)` computes \(e^x-1\) using a specialized algorithm, **not simply executing Java's `Math.exp(x) - 1` in the same steps**. Thus, the function maintains high precision when x is very small.

### Choosing `expm1` Based on Formula Intent

If the formula needs the **growth factor** \(e^r\), use `exp(r)`. If it needs the **increase relative to 1** \(e^r-1\), use `expm1(r)`:

```java
double continuousRate = 1e-12;
double relativeIncrease = Math.expm1(continuousRate);
```

For very small interest rates or percentage changes, `relativeIncrease` is the needed quantity. Using `exp` and subtracting 1 can lose significant digits.

For very negative inputs, `Math.expm1(-1000.0)` returns `-1.0` because \(e^{-1000}-1\) rounds to -1. Conversely, `Math.exp(-1000.0)` rounds to zero. This is not a contradiction, because **the two functions return two different quantities**.

## 6. Why Can `Math.log(1.0 + x)` Lose Precision?

A similar mechanism occurs when \(x\) is very close to 0. The operation `1.0 + x` can round to exact `1.0` **before** `Math.log` is even called:

```java
double x = 1e-16;
double naive = Math.log(1.0 + x);
double stable = Math.log1p(x);

System.out.println(naive);  // 0.0
System.out.println(stable); // 1.0E-16
```

Mathematically, \(\ln(1+x) \approx x\) when \(x\) is small. `Math.log(1.0 + x)` has no way of knowing that the input `1.0` was the rounded result of the sum `1.0 + 1e-16`; the information was already lost **before calling log**.

`Math.log1p(x)` computes \(\ln(1+x)\) with an algorithm that preserves precision for small x. It is suitable for:

- Log-return formulas \(\ln(1+r)\) with very small return rate `r`.
- Handling probabilities and transformations expressed as relative changes around 1.
- Algorithms needing the logarithm of the sum `1+x` where `x` is a small independent input.

Example computing *log-return*:

```java
double smallReturn = 1e-12;
double logReturn = Math.log1p(smallReturn);
```

You should not use `log1p` just to take an ordinary logarithm: `Math.log1p(100.0)` is \(\ln(101)\), **different** from `Math.log(100.0)` which is \(\ln(100)\).

## 7. Domain: `log(x)` Differs from `log1p(x)`

The logarithm functions have different real-valued domains:

| Function | Inputs Yielding Ordinary Real Values | Boundary Point | Invalid Side |
| --- | --- | --- | --- |
| `Math.log(x)` | `x > 0.0` | `x == ±0.0` → `-Infinity` | `x < 0.0` → `NaN` |
| `Math.log10(x)` | `x > 0.0` | `x == ±0.0` → `-Infinity` | `x < 0.0` → `NaN` |
| `Math.log1p(x)` | `x > -1.0` | `x == -1.0` → `-Infinity` | `x < -1.0` → `NaN` |

`Math.log1p(-0.5)` is a finite negative value because `1-0.5 = 0.5 > 0`, whereas `Math.log(-0.5)` returns NaN.

```java
System.out.println(Math.log1p(-1.0)); // -Infinity
System.out.println(Math.log1p(-2.0)); // NaN
System.out.println(Math.log(-1.0));   // NaN
```

Signed zero is a special case:

```java
System.out.println(Math.log1p(-0.0)); // -0.0
System.out.println(Math.expm1(-0.0)); // -0.0
System.out.println(Math.log(-0.0));   // -Infinity
```

`log1p(-0.0)` and `expm1(-0.0)` **preserve negative zero**. Meanwhile, `log(-0.0)` returns negative infinity, because the logarithm at zero is on the domain boundary. Do not infer that the two functions are interchangeable just because x is near 0.

If the result must be finite, check the input domain **and** check the output; special rules can yield `Infinity`/`NaN` without raising an exception.

## 8. `Infinity`, `NaN`, and Overflow/Underflow Cases

With `double`, the five functions have special real-number behaviors. The following table lists notable results:

| Input | `exp(x)` | `log(x)` | `log10(x)` | `expm1(x)` | `log1p(x)` |
| --- | --- | --- | --- | --- | --- |
| `+0.0` | `1.0` | `-Infinity` | `-Infinity` | `+0.0` | `+0.0` |
| `-0.0` | `1.0` | `-Infinity` | `-Infinity` | `-0.0` | `-0.0` |
| `+Infinity` | `+Infinity` | `+Infinity` | `+Infinity` | `+Infinity` | `+Infinity` |
| `-Infinity` | `+0.0` | `NaN` | `NaN` | `-1.0` | `NaN` |
| `NaN` | `NaN` | `NaN` | `NaN` | `NaN` | `NaN` |
| `-1.0` | Positive finite | `NaN` | `NaN` | Negative finite | `-Infinity` |

Note: `Math.exp(-Infinity)` is **positive zero**, not negative zero. `Math.expm1(-Infinity)` is -1.0. `Math.log1p(-Infinity)` is NaN because \(1+(-\infty)\) is not in the positive real logarithm domain.

### No Automatic Exceptions for Negative Log or Exp Overflow

`Math.log(-2.0)` does not throw `IllegalArgumentException`; it returns `NaN`. `Math.exp(800.0)` does not throw `ArithmeticException`; it returns `Infinity`. These are special floating-point values per the API rules.

To classify:

```java
double result = Math.exp(800.0);
System.out.println(Double.isInfinite(result)); // true
System.out.println(Double.isFinite(result));   // false
```

`Double.isFinite` only tells whether the result is finite. It does not guarantee **no loss of precision**, and `0.0` from underflow is still considered finite. If you need to prevent underflow or control relative precision, you must analyze the input domain and the specific algorithm.

## 9. Accuracy: `Math` vs. `StrictMath`

Both `Math` and `StrictMath` provide `exp`, `log`, `log10`, `expm1`, and `log1p` with corresponding semantics and special cases.

- **`Math`:** standard API for general computation; these functions have accuracy requirements such as a maximum error around **1 ulp** and *semi-monotonicity* as specified per method. The JVM may use optimized implementations.
- **`StrictMath`:** designed to deliver reproducible results across platforms for specified functions, based on standardized rules/algorithms. It does not mean it is always closer to the exact mathematical result than `Math` for every input.
- Since Java 17, Java floating-point expressions have always-strict semantics per language changes; this **does not make `Math` and `StrictMath` the same API or force them to return identical bits everywhere**.

Example:

```java
double fastOrDefault = Math.exp(1.0);
double reproducible = StrictMath.exp(1.0);

String first = String.format(java.util.Locale.ROOT,
        "%.6f", fastOrDefault);
String second = String.format(java.util.Locale.ROOT,
        "%.6f", reproducible);
// Both may display "2.718282" when formatted to 6 decimal places.
```

**You should not claim `Math.exp(x) == StrictMath.exp(x)` is always true**, nor claim `StrictMath` is always faster/slower on every JVM; evaluate accuracy, reproducibility, and performance according to the contract and environment.

`StrictMath.expm1`/`StrictMath.log1p` remain useful for **stabilizing calculations near 0**. The deciding factor for choosing `expm1` over `exp-1`, or `log1p` over `log(1+x)`, is the numerical formula to compute, not just the class name.

## 10. Commonly Applied Formulas and Limits

### Computing Small Growth

If you need the growth portion \(e^{rt}-1\):

```java
double rateTimesTime = 1e-12;
double relativeGrowth = Math.expm1(rateTimesTime);
```

`relativeGrowth` preserves tiny signals better than `Math.exp(rateTimesTime)-1.0`. If you only need the multiplier \(e^{rt}\), use `Math.exp(rateTimesTime)`.

### Log-Return

Given a relative change `r`, with `r > -1`:

```java
double r = 1e-12;
double logReturn = Math.log1p(r);
```

If `r == -1`, the result is `-Infinity`. If `r < -1`, the result is `NaN`. Business contracts may require rejecting invalid data before calling the function.

### Function Composition Is an Approximate Inverse, Not Bit-Exact

Mathematically, under appropriate conditions:

\[
\ln(e^x)=x,\qquad e^{\ln(x)}=x \quad(x>0).
\]

However, with floating-point arithmetic:

- `Math.log(Math.exp(800.0))` returns `Infinity` because `exp(800)` overflowed.
- `Math.log(Math.exp(-800.0))` returns `-Infinity` because `exp(-800)` underflowed to 0.
- With small `x`, `Math.log(Math.exp(x))` may return 0 instead of x; `Math.log1p(Math.expm1(x))` can preserve x better near 0.
- With normal positive x, `Math.exp(Math.log(x))` is still an approximation; do not use `==` comparison as an absolute mathematical guarantee.

### Computing in Log Space to Avoid Product Overflow/Underflow

If multiplying many very small positive factors, you can add `Math.log(p)` instead of multiplying them all directly:

```java
double p = 1e-200;
double q = 1e-200;
double directProduct = p * q;      // underflow: 0.0
double logProduct = Math.log(p) + Math.log(q); // finite
```

This is a strategy of storing the **log of the product**, which cannot automatically recover the original product as a `double` if it remains smaller than the representable range. For probability models and statistical algorithms, this is often a practical benefit.

## 11. Standalone Java 17+ Program

Create file **`ExpLogDemo.java`**:

```java
import java.util.Locale;

public class ExpLogDemo {
    public static void main(String[] args) {
        System.out.println("expZero=" + Math.exp(0.0));
        System.out.println("expNegativeZero=" + Math.exp(-0.0));
        System.out.println("logOne=" + Math.log(1.0));
        System.out.println("logTenBase10=" + Math.log10(10.0));
        System.out.println("logThousandBase10=" + Math.log10(1000.0));

        double x = 1e-16;
        System.out.println("naiveExpMinusOne=" + (Math.exp(x) - 1.0));
        System.out.println("stableExpMinusOne=" + Math.expm1(x));
        System.out.println("naiveLogOnePlus=" + Math.log(1.0 + x));
        System.out.println("stableLogOnePlus=" + Math.log1p(x));
        System.out.println("composedNaive=" + Math.log(Math.exp(x)));
        System.out.println("composedStable=" +
                Math.log1p(Math.expm1(x)));

        System.out.println("expOverflow=" + Math.exp(800.0));
        System.out.println("expUnderflow=" + Math.exp(-800.0));
        System.out.println("expm1NegativeInfinity=" +
                Math.expm1(Double.NEGATIVE_INFINITY));
        System.out.println("expPositiveInfinity=" +
                Math.exp(Double.POSITIVE_INFINITY));
        System.out.println("expNegativeInfinity=" +
                Math.exp(Double.NEGATIVE_INFINITY));

        System.out.println("logZero=" + Math.log(0.0));
        System.out.println("logNegativeZero=" + Math.log(-0.0));
        System.out.println("logNegative=" + Math.log(-1.0));
        System.out.println("log10Zero=" + Math.log10(0.0));
        System.out.println("log10Negative=" + Math.log10(-10.0));
        System.out.println("logPositiveInfinity=" +
                Math.log(Double.POSITIVE_INFINITY));

        System.out.println("log1pMinusOne=" + Math.log1p(-1.0));
        System.out.println("log1pBelowMinusOne=" + Math.log1p(-2.0));
        System.out.println("expm1NegativeZero=" + Math.expm1(-0.0));
        System.out.println("log1pNegativeZero=" + Math.log1p(-0.0));
        System.out.println("nanInput=" + Math.log1p(Double.NaN));

        double overflow = Math.exp(800.0);
        System.out.println("overflowIsInfinite=" +
                Double.isInfinite(overflow));
        System.out.println("overflowIsFinite=" +
                Double.isFinite(overflow));

        System.out.println("mathExpSixDecimals=" +
                String.format(Locale.ROOT, "%.6f", Math.exp(1.0)));
        System.out.println("strictExpSixDecimals=" +
                String.format(Locale.ROOT, "%.6f", StrictMath.exp(1.0)));
        System.out.println("logOneHalfSixDecimals=" +
                String.format(Locale.ROOT, "%.6f", Math.log1p(-0.5)));
        System.out.println("logBaseTwoEightSixDecimals=" +
                String.format(Locale.ROOT, "%.6f",
                        Math.log(8.0) / Math.log(2.0)));
    }
}
```

Compile and run with JDK 17+:

```bash
javac ExpLogDemo.java
java ExpLogDemo
```

**Expected output** on JDK 17 when using this exact example:

```text
expZero=1.0
expNegativeZero=1.0
logOne=0.0
logTenBase10=1.0
logThousandBase10=3.0
naiveExpMinusOne=0.0
stableExpMinusOne=1.0E-16
naiveLogOnePlus=0.0
stableLogOnePlus=1.0E-16
composedNaive=0.0
composedStable=1.0E-16
expOverflow=Infinity
expUnderflow=0.0
expm1NegativeInfinity=-1.0
expPositiveInfinity=Infinity
expNegativeInfinity=0.0
logZero=-Infinity
logNegativeZero=-Infinity
logNegative=NaN
log10Zero=-Infinity
log10Negative=NaN
logPositiveInfinity=Infinity
log1pMinusOne=-Infinity
log1pBelowMinusOne=NaN
expm1NegativeZero=-0.0
log1pNegativeZero=-0.0
nanInput=NaN
overflowIsInfinite=true
overflowIsFinite=false
mathExpSixDecimals=2.718282
strictExpSixDecimals=2.718282
logOneHalfSixDecimals=-0.693147
logBaseTwoEightSixDecimals=3.000000
```

The four `naive...` and `stable...` lines demonstrate the essential difference: `exp(x)-1` and `log(1+x)` can lose signals near 0; `expm1` and `log1p` preserve precision better. The `Infinity`/`NaN` lines demonstrate why input and output domains must be checked. The two `Math`/`StrictMath` lines use **six-digit formatting**, without claiming every binary digit of the two results is identical.

## 12. Common Mistakes

| Claim | Correct Understanding |
| --- | --- |
| "`Math.log` in Java defaults to base 10." | False: `Math.log` is natural logarithm; `Math.log10` is base 10. |
| "`Math.exp(x) - 1` and `Math.expm1(x)` always have the same precision." | False: `expm1` is better near x = 0 by avoiding cancellation. |
| "`Math.log(1+x)` is identical to `Math.log1p(x)` on a computer for all x." | False: the `1+x` step can round to 1. |
| "`Math.log1p(x)` means the log of x plus 1 after taking the log." | False: it computes \(\ln(1+x)\), not \(\ln(x)+1\). |
| "`Math.expm1(x)` computes \(e^{x-1}\)." | False: it computes \(e^x-1\). |
| "`Math.log(-1)` must throw an exception." | For `double` floating-point, the result is `NaN`, not an automatic exception. |
| "`Math.log1p(-1)` gives NaN." | False: exactly at boundary -1 it returns `-Infinity`; only below -1 gives NaN. |
| "`Math.exp(800)` will always give a finite `double`." | False: it overflows to `Infinity`. |
| "`Math.exp(-800)` equals 0 mathematically." | False: it is underflow to zero in `double` representation. |
| "`Math.log1p(-0.0)` changes sign to positive zero." | False: the API preserves `-0.0`. |
| "`StrictMath` always gives more accurate digits than `Math`." | There is no such general guarantee; a key goal of `StrictMath` is result reproducibility. |
| "`exp(log(x)) == x` is always true." | It is a mathematical identity in the proper domain, but floating-point implementations have rounding and special cases. |

## 13. Function Selection Checklist

1. **Do you need exponential or logarithmic?** `exp(x)` computes \(e^x\); `log(x)` computes \(\ln x\); `log10(x)` computes \(\log_{10}x\).
2. **Does the problem subtract 1 after the exponential?** If the formula is \(e^x-1\), prefer `expm1(x)`, especially when `x` is near 0.
3. **Does the problem take the log of 1 plus x?** If the formula is \(\ln(1+x)\), prefer `log1p(x)`, especially when `x` is near 0.
4. **Is the domain valid?** `log`/`log10` require positive x; `log1p` requires x greater than -1 for ordinary finite results.
5. **Is there a risk of overflow or underflow?** `exp` can become infinity/zero. Consider log space and handle `Double.isFinite` appropriately.
6. **Do `NaN`, Infinity, and signed zero matter?** Do not rely on integer exceptions; use domain checks and `Double.isNaN`/`isInfinite`/`isFinite`.
7. **Do you need cross-JVM reproducibility?** Consider `StrictMath` as required; do not assume it is always faster or more accurate.
8. **Do you need bit-identical results after function composition?** Unless guaranteed, use appropriate absolute/relative tolerances instead of `==` for approximate floating-point results.

**Key takeaway:** `exp` and `log` are the two fundamental base-\(e\) functions, `log10` is base 10; `expm1` and `log1p` are for expressions **very close to 0 that easily lose significant digits**. Choosing the right function is often more important than trying to round results after each step.