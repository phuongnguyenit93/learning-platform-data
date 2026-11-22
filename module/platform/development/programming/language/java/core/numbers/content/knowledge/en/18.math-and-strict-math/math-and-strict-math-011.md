# Domain, NaN, Infinity, and Accuracy Specified by Javadoc: `Math` and `StrictMath`

When calling `Math.sqrt`, `Math.log`, `Math.pow`, `Math.hypot`, or `StrictMath.exp`, knowing the mathematical formula is not enough. A Java program must also know **which inputs are valid, what happens with IEEE 754 special values, the error bounds of the result, and the reproducibility the API actually guarantees**.

A brief example:

```java
System.out.println(Math.sqrt(-1.0)); // NaN
System.out.println(Math.log(0.0));   // -Infinity
System.out.println(Math.pow(Double.NaN, 0.0)); // 1.0
```

All three results above make sense under **each method's contract** and cannot be deduced from a blanket rule like "unusual inputs always throw an exception" or "any NaN input always produces NaN".

This lesson uses **Java 17+**, focusing on how to **read and apply Javadoc**. When deploying on a different Java version, check the documentation for the exact version in use. Official reference sources:

- [Javadoc Java 17 — java.lang.Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html)
- [Javadoc Java 17 — java.lang.StrictMath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html)

## 1. "Domain" in Mathematics vs. in `double`

Real mathematics gives \(\sqrt{x}\) the domain \(x\geq 0\), \(\ln(x)\) the domain \(x>0\), and \(\arcsin(x)\) the domain \(-1\leq x\leq1\). However, `double` values also include:

- `Double.NaN`: a Not-a-Number result under IEEE 754 semantics.
- `Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY`: signed infinities.
- `+0.0` and `-0.0`: zeros with different sign bits, even though `+0.0 == -0.0` is `true`.
- **Subnormal** values very close to 0; overflow or underflow can turn results into infinity or zero.

**The ordinary real domain** is only the first step in reading documentation. Javadoc also specifies **special cases**: when receiving NaN, infinity, signed zero, out-of-domain numbers, or special combinations of two/three parameters, what a specific method must return.

For example, with `sqrt`:

```java
double a = Math.sqrt(4.0); // 2.0
double b = Math.sqrt(-1.0); // NaN
double c = Math.sqrt(-0.0); // -0.0
```

`sqrt(-0.0)` is **not** treated as the square root of an invalid negative number: Javadoc explicitly states it must return **zero with the same sign**. Conversely, `sqrt(-1.0)` returns NaN.

Do not equate "NaN" with "exception". In floating-point computation, many methods signal status through the **return value itself**.

## 2. Why Cannot a Single Blanket NaN Rule Table Be Used for Every Function?

Some functions propagate NaN in the usual way, but **special cases can take precedence**:

| Java Expression | Result | Contract to Recognize |
| --- | --- | --- |
| `Math.sqrt(-1.0)` | `NaN` | Square root of a real negative number has no real result |
| `Math.sqrt(-0.0)` | `-0.0` | Preserves zero sign |
| `Math.log(+0.0)` | `-Infinity` | Zero is the boundary of the logarithm |
| `Math.log(-0.0)` | `-Infinity` | Both zeros yield negative infinity |
| `Math.log(-1.0)` | `NaN` | Out-of-domain negative input |
| `Math.exp(Double.NEGATIVE_INFINITY)` | `+0.0` | Limit of \(e^x\) as \(x\to-\infty\) |
| `Math.pow(Double.NaN, 0.0)` | `1.0` | Exponent equal to zero is given precedence |
| `Math.pow(-2.0, 0.5)` | `NaN` | Negative base with finite non-integer exponent |
| `Math.hypot(Double.POSITIVE_INFINITY, Double.NaN)` | `Infinity` | Infinite argument takes precedence per Javadoc |
| `Math.fma(Double.POSITIVE_INFINITY, 0.0, 1.0)` | `NaN` | Infinity times zero product is a special case |
| `Math.min(-0.0, +0.0)` | `-0.0` | Negative zero is smaller than positive zero per `min` contract |
| `Math.max(-0.0, +0.0)` | `+0.0` | Positive zero is larger than negative zero per `max` contract |

Subtle point: **`Math.pow(Double.NaN, 0.0)` returns 1.0**, even though the first argument is NaN. **`Math.hypot(Infinity, NaN)` returns infinity**, despite the presence of NaN. Claiming "any NaN parameter must produce NaN" would be false.

Nor should you assume `Math.min`/`Math.max` behave identically to `<`/`>` operators in every case. They have explicit rules for signed zero and NaN.

## 3. Domain and Representative Boundary Cases Table

| Method | Ordinary Finite Real Domain | Boundary / Out-of-Domain Inputs |
| --- | --- | --- |
| `sqrt(x)` | \(x\geq0\) | `x<0` → NaN; `-0.0` → -0.0; `+Infinity` → +Infinity |
| `cbrt(x)` | All real x | Negative numbers give negative cube root; `-0.0` → -0.0; ±Infinity preserves sign |
| `log(x)` | \(x>0\) | ±0.0 → -Infinity; negative x → NaN; +Infinity → +Infinity |
| `log10(x)` | \(x>0\) | ±0.0 → -Infinity; negative x → NaN |
| `log1p(x)` | \(x>-1\) | `-1.0` → -Infinity; x less than -1 → NaN; ±0.0 preserves sign |
| `exp(x)` | All real x | -Infinity → +0.0; +Infinity → +Infinity; can overflow/underflow |
| `expm1(x)` | All real x | -Infinity → -1.0; ±0.0 preserves sign; can overflow |
| `asin(x)`, `acos(x)` | \(-1\leq x\leq1\) | `abs(x)>1` → NaN |
| `sin(x)`, `cos(x)`, `tan(x)` | All real x | NaN or ±Infinity → NaN; `sin`/`tan` preserve zero sign |
| `pow(a,b)` | Depends on both a and b | `a<0`, finite non-integer b → NaN; detailed rules for zero, NaN, infinity |
| `hypot(x,y)` | All finite real x,y | Any Infinity → +Infinity even if the other argument is NaN |
| `fma(a,b,c)` | Floating-point \(a\times b+c\) | Infinity × zero → NaN; any NaN → NaN |
| `min(a,b)` / `max(a,b)` for `double` | All finite values | If either parameter is NaN → NaN; distinguishes -0.0 and +0.0 |

This table is a lookup map, **not a replacement for the full special cases list in each Javadoc**. In particular, `pow` has numerous combinations of exponent 0, ±Infinity, base ±0.0, and even/odd integer exponents; when evaluating a boundary case, read the exact `pow` section.

**A method not throwing an exception** in one example does not prove the entire API never throws exceptions in any context. For instance, integer primitive operations like `Math.addExact` throw `ArithmeticException` on overflow, whereas `Math.sqrt(-1.0)` returns NaN. Each method has its own contract.

## 4. `NaN`, ±Infinity, and Proper Checks

Use floating-point classification APIs:

```java
double x = Math.log(-1.0);

System.out.println(Double.isNaN(x));      // true
System.out.println(Double.isInfinite(x)); // false
System.out.println(Double.isFinite(x));   // false
```

`Double.isFinite(x)` returns `true` only for finite values, including `+0.0`, `-0.0`, and subnormals. `Float` has corresponding `Float.isNaN`, `Float.isInfinite`, and `Float.isFinite`.

**Do not check for NaN using `x == Double.NaN`.** Under floating-point comparison, NaN is not equal to itself:

```java
double x = Double.NaN;
System.out.println(x == Double.NaN); // false
System.out.println(Double.isNaN(x));  // true
```

When a program requires a **finite result**, validate after computing:

```java
static double requireFinite(double result) {
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("Result is not finite");
    }
    return result;
}
```

This is an illustrative method placed in a class. The exception in the helper **is explicitly thrown by the programmer**; `Math` itself does not throw a similar exception upon encountering abnormal values. Checking `isFinite` still **does not detect digit loss from rounding**, nor does it prevent results from underflowing to zero.

## 5. `+0.0` and `-0.0`: Equal Yet Not Arbitrarily Interchangeable

`float` and `double` types have a dedicated sign bit for zero. The arithmetic operator `==` treats both zeros as equal:

```java
System.out.println(+0.0 == -0.0); // true
```

However, Javadoc specifies that many functions must inspect the sign:

- `Math.sqrt(-0.0)` → `-0.0`.
- `Math.cbrt(-0.0)` → `-0.0`.
- `Math.sin(-0.0)` and `Math.tan(-0.0)` → `-0.0`.
- `Math.expm1(-0.0)` and `Math.log1p(-0.0)` → `-0.0`.
- `Math.log(-0.0)` → `-Infinity`.
- `Math.exp(-0.0)` → `1.0`.
- `Math.min(+0.0,-0.0)` → `-0.0`; `Math.max(+0.0,-0.0)` → `+0.0`.

To distinguish bits:

```java
long a = Double.doubleToRawLongBits(+0.0); // 0x0000000000000000
long b = Double.doubleToRawLongBits(-0.0); // 0x8000000000000000
boolean sameBits = a == b; // false
```

`Double.compare(+0.0, -0.0)` also distinguishes signed zero, unlike `==`. When data flows through algorithms involving division or one-sided limits, preserving or normalizing zero's sign can affect outcomes. Ordinary applications that do not need to distinguish zero signs should still **normalize intentionally**, rather than assuming bits and subsequent operations are identical just because `==` is true.

## 6. What Is ULP? What Does "Accuracy Within 1 ulp" Mean?

`ulp` stands for *unit in the last place*. Within a `double` value region, the spacing between representable real numbers **changes with the magnitude of the number**. Near `1.0`, the gap between `1.0` and the nearest larger `double` is:

```java
System.out.println(Math.ulp(1.0));       // 2.220446049250313E-16
System.out.println(Math.nextUp(1.0));    // 1.0000000000000002
```

`Math` Javadoc uses ULP to define **error bounds relative to the exact mathematical result**, rather than a fixed number of decimal digits. With the phrasing "error at most 1 ulp", the bound is measured on the **binary floating-point grid at the magnitude of the result**, not "error at most 1.0 real unit" or "accurate in one last decimal digit".

A mental picture:

```text
... 1.0000000000000000
... 1.0000000000000002   (next double number)
... 1.0000000000000004
       ^ spacing near 1.0 is about 2.22 × 10^-16
```

Near very large numbers, ULP is larger; near zero, subnormal spacing is tiny. Relative precision and absolute error must be analyzed within the actual data domain.

### `Math.ulp` Does Not Measure the Actual Error of a Call

`Math.ulp(result)` returns the size of one representation step around `result`; it **does not know the exact mathematical value** to compute `abs(result - exact)`.

Thus:

```java
double value = Math.exp(1.0);
double spacing = Math.ulp(value);
```

`spacing` is one ULP size around the obtained number, **not a report** that `Math.exp(1.0)` is actually off by `spacing`.

To evaluate a function's error in standard testing, you need a higher-precision reference value or a reliable comparison method; you cannot deduce the error from a single call to `Math.ulp`.

## 7. "Correctly Rounded", 0.5/1/2 ulp Bounds, and Semi-Monotonic

Javadoc distinguishes guarantee levels:

| Term | Meaning |
| --- | --- |
| **Correctly rounded** | Selects the right floating-point result under the specified rounding rule from the exact mathematical result |
| **Within 0.5 ulp** | Very tight error bound; a method accurate to this level returns the representable number closest to the true result (with an appropriate tie rule) |
| **Within 1 ulp** | Deviation bounded by the number-grid spacing; **not** necessarily the nearest rounded result in every case |
| **Within 2 ulp** | Looser bound than 1 ulp, applied to certain functions explicitly noted in Javadoc |
| **Semi-monotonic** | Over intervals where the mathematical function increases (or decreases), the floating-point approximation must not reverse direction, per each function's requirement |

`Math.sqrt` is described by Java 17 Javadoc as the **correctly rounded positive square root**: this is a specific guarantee. Meanwhile, functions such as `Math.sin`, `Math.log`, and `Math.exp` are specified as **within 1 ulp** and **semi-monotonic**, with no promise that every result is rounded to the nearest bit.

Keep in mind:

1. **Read the ULP number in the exact method entry**, do not apply "1 ulp for all of `Math`".
2. **Semi-monotonic does not mean a function increases across the entire real line.** `sin(x)` naturally has increasing and decreasing segments; the constraint is about the approximation preserving direction on intervals where the mathematical function is monotonic.
3. **Within 1 ulp does not imply identical bits across all JVMs.** Two implementations can return different results while both remaining within Javadoc limits.
4. **Accuracy guarantees do not replace value-domain guarantees.** A function with a ULP specification still has special cases for NaN/Infinity/signed zero.

### Examples of Levels per Method

According to Java 17 Javadoc:

| `Math` method | Associated Guarantee |
| --- | --- |
| `sqrt(double)` | Correctly rounded |
| `sin(double)`, `cos(double)`, `tan(double)` | Within **1 ulp**, semi-monotonic |
| `exp(double)`, `log(double)`, `log10(double)` | Within **1 ulp**, semi-monotonic |
| `expm1(double)`, `log1p(double)` | Within **1 ulp**, semi-monotonic |
| `pow(double,double)` | Within **1 ulp**, semi-monotonic |
| `hypot(double,double)` | Within **1 ulp**; semi-monotonic in one variable when the other is fixed |
| `atan2(double,double)` | Within **2 ulp**, semi-monotonic |
| `sinh(double)`, `cosh(double)`, `tanh(double)` | Within **2.5 ulp** per Javadoc |
| `fma(double,double,double)` | Computes product then sum as if with infinite precision/range, **rounded once to nearest-even** |

Do not falsely deduce that a "2.5 ulp" function is always less accurate than a "1 ulp" function. That is the **maximum error bound permitted by the API**, not the actual error magnitude on every call.

### Why Does `fma` Differ from `a * b + c`?

```java
double combined = Math.fma(a, b, c);
double separate = a * b + c;
```

`Math.fma` rounds **once** after mathematically computing \(a\times b+c\), whereas the ordinary expression rounds the product and then rounds the sum. The two results can differ by a few bits in sensitive cases. This is by **contract**, not because some CPU "happened to compute better".

`Math.fma(Double.POSITIVE_INFINITY, 0.0, 1.0)` returns NaN per the special case for infinity times zero, without throwing an exception.

## 8. Where Does `Math` Differ from `StrictMath`?

**Both** provide numerous floating-point math methods and special values according to Java's contract. However, **bit-for-bit result reproducibility** is not the same:

- `Math` allows different implementations of **certain functions** across platforms/JVMs, provided they **meet accuracy and Javadoc constraints**. This paves the way for intrinsics, CPU instructions, or faster native libraries.
- `StrictMath` requires certain math functions to behave compatibly with algorithms published in **fdlibm 5.3**; the primary goal is cross-platform **reproducibility**, not a promise of "always more accurate than `Math`".
- Since Java 17 (JEP 306), Java floating-point expressions have returned to *always-strict* semantics. That **does not erase the difference between `Math` and `StrictMath` contracts**.

Java 17 `StrictMath` Javadoc explicitly lists the functions that must follow fdlibm, including `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `exp`, `log`, `log10`, `cbrt`, `atan2`, `pow`, `sinh`, `cosh`, `tanh`, `hypot`, `expm1`, and `log1p`.

**Do not generalize that every method in `StrictMath` runs fdlibm**; other methods have their own specifications. Nor does the name `StrictMath` **guarantee every call runs slower or is more accurate than `Math`**.

An example of a practical requirement:

```java
double fastOrPlatform = Math.exp(1.0);
double specReproducible = StrictMath.exp(1.0);
```

Both values may match in the current environment, but **do not use a test `Math.exp(x) == StrictMath.exp(x)` for all x and all JVMs as a guarantee**. If a workflow requires bit reproducibility in an fdlibm-group function, consider `StrictMath`, while also pinning the Java version, input data, and environment as needed.

## 9. Integer Methods: Precision and Overflow Have Different Contracts

The `Math`/`StrictMath` topic is not just about `double`. Several integer APIs like `Math.addExact`, `Math.multiplyExact`, and `Math.toIntExact` **throw `ArithmeticException` on overflow**.

Conversely, `Math.abs(int)` has a special case:

```java
int minimum = Integer.MIN_VALUE;
System.out.println(Math.abs(minimum)); // -2147483648
```

Because the `int` range is `[-2^31, 2^31-1]`, the mathematical absolute value of `Integer.MIN_VALUE` is unrepresentable as an `int`. `Math.abs(minimum)` by its legacy contract returns that same negative number. **Do not interpret the name `abs` as guaranteeing a non-negative result for every `int`**.

If you need to detect this:

```java
try {
    int exact = Math.absExact(Integer.MIN_VALUE);
} catch (ArithmeticException ex) {
    System.out.println("abs overflow detected");
}
```

`Math.absExact` (available in Java 17) throws an exception when the absolute value cannot fit in the integer type. This is a **different error mechanism** compared to the NaN/Infinity values of many `double` functions.

In summary, check **parameter types, overloads, and the specific contract** before inferring domain and error reporting behavior.

## 10. Building Input/Output Validation Based on Application Contracts

Javadoc tells you **what Java will return**; it does not decide whether that value is permissible by your application.

Example of an application requiring the square root of a finite non-negative number, where the result must also be finite:

```java
static double checkedSqrt(double x) {
    if (!Double.isFinite(x) || x < 0.0) {
        throw new IllegalArgumentException("Expected finite nonnegative x");
    }
    double answer = Math.sqrt(x);
    if (!Double.isFinite(answer)) {
        throw new ArithmeticException("Non-finite square root");
    }
    return answer;
}
```

This is an illustrative method placed in a class. Because `-0.0 < 0.0` is false, the helper **accepts -0.0**, and `Math.sqrt(-0.0)` will return **-0.0**. If the contract needs to exclude or normalize negative zero, add an explicit rule; `x < 0.0` alone is not enough.

For natural logarithm:

```java
static double checkedLog(double x) {
    if (!Double.isFinite(x) || x <= 0.0) {
        throw new IllegalArgumentException("Expected finite positive x");
    }
    double answer = Math.log(x);
    if (!Double.isFinite(answer)) {
        throw new ArithmeticException("Non-finite logarithm");
    }
    return answer;
}
```

Here `x <= 0.0` **rejects both +0.0 and -0.0**. Pairing `Double.isFinite` with the positive domain cleanly filters out NaN/Infinity rather than letting them propagate through formulas.

### When IEEE 754 Values Should Be Accepted

Research or simulation systems may intentionally keep `NaN`/Infinity as computation states. In that case, do not use helpers that forbid all non-finite values; instead have documented handling:

```java
double result = Math.log(input);
if (Double.isNaN(result)) {
    // Designed NaN handling path
} else if (Double.isInfinite(result)) {
    // Infinity handling path
} else {
    // Finite result
}
```

This is an illustrative snippet inside a method with a declared `input` variable. Do not silently convert NaN to zero just to "keep the program running": zero is also a valid mathematical value, so doing so masks data errors.

## 11. Standalone Java 17+ Program and Verifiable Output

Save as **`MathJavadocContractDemo.java`**:

```java
import java.util.Locale;

public class MathJavadocContractDemo {
    static double checkedLog(double x) {
        if (!Double.isFinite(x) || x <= 0.0) {
            throw new IllegalArgumentException("Expected finite positive x");
        }
        return Math.log(x);
    }

    public static void main(String[] args) {
        System.out.println("sqrtNegative=" + Math.sqrt(-1.0));
        System.out.println("sqrtNegativeZero=" + Math.sqrt(-0.0));
        System.out.println("cbrtNegativeZero=" + Math.cbrt(-0.0));
        System.out.println("logZero=" + Math.log(0.0));
        System.out.println("logNegativeZero=" + Math.log(-0.0));
        System.out.println("logNegative=" + Math.log(-1.0));
        System.out.println("log1pMinusOne=" + Math.log1p(-1.0));
        System.out.println("expm1MinusZero=" + Math.expm1(-0.0));

        System.out.println("powNanZero=" + Math.pow(Double.NaN, 0.0));
        System.out.println("powNegativeFraction=" + Math.pow(-2.0, 0.5));
        System.out.println("hypotInfAndNan=" +
                Math.hypot(Double.POSITIVE_INFINITY, Double.NaN));
        System.out.println("fmaInfinityTimesZero=" +
                Math.fma(Double.POSITIVE_INFINITY, 0.0, 1.0));

        System.out.println("minSignedZero=" + Math.min(+0.0, -0.0));
        System.out.println("maxSignedZero=" + Math.max(+0.0, -0.0));
        System.out.println("zeroNumericEqual=" + (+0.0 == -0.0));
        System.out.println("zeroSameBits=" +
                (Double.doubleToRawLongBits(+0.0) ==
                 Double.doubleToRawLongBits(-0.0)));

        System.out.println("ulpOne=" + Math.ulp(1.0));
        System.out.println("nextUpOne=" + Math.nextUp(1.0));

        double outOfDomain = Math.log(-1.0);
        System.out.println("nanDetected=" + Double.isNaN(outOfDomain));
        System.out.println("nanFinite=" + Double.isFinite(outOfDomain));
        System.out.println("nanEqualsSelf=" +
                (Double.NaN == Double.NaN));

        System.out.println("expOverflow=" + Math.exp(800.0));
        System.out.println("expUnderflow=" + Math.exp(-800.0));
        System.out.println("overflowIsInfinite=" +
                Double.isInfinite(Math.exp(800.0)));

        System.out.println("mathExpSixDigits=" +
                String.format(Locale.ROOT, "%.6f", Math.exp(1.0)));
        System.out.println("strictExpSixDigits=" +
                String.format(Locale.ROOT, "%.6f", StrictMath.exp(1.0)));

        System.out.println("absMinimum=" + Math.abs(Integer.MIN_VALUE));
        try {
            Math.absExact(Integer.MIN_VALUE);
            System.out.println("absExact=notDetected");
        } catch (ArithmeticException ex) {
            System.out.println("absExact=detected");
        }

        try {
            checkedLog(0.0);
            System.out.println("checkedLogZero=notDetected");
        } catch (IllegalArgumentException ex) {
            System.out.println("checkedLogZero=detected");
        }
        System.out.println("checkedLogOne=" + checkedLog(1.0));
    }
}
```

Compile and run:

```bash
javac MathJavadocContractDemo.java
java MathJavadocContractDemo
```

**Output for the selected values**:

```text
sqrtNegative=NaN
sqrtNegativeZero=-0.0
cbrtNegativeZero=-0.0
logZero=-Infinity
logNegativeZero=-Infinity
logNegative=NaN
log1pMinusOne=-Infinity
expm1MinusZero=-0.0
powNanZero=1.0
powNegativeFraction=NaN
hypotInfAndNan=Infinity
fmaInfinityTimesZero=NaN
minSignedZero=-0.0
maxSignedZero=0.0
zeroNumericEqual=true
zeroSameBits=false
ulpOne=2.220446049250313E-16
nextUpOne=1.0000000000000002
nanDetected=true
nanFinite=false
nanEqualsSelf=false
expOverflow=Infinity
expUnderflow=0.0
overflowIsInfinite=true
mathExpSixDigits=2.718282
strictExpSixDigits=2.718282
absMinimum=-2147483648
absExact=detected
checkedLogZero=detected
checkedLogOne=0.0
```

The tests focus on **special cases explicitly defined by Javadoc**. The two formatted lines for `Math.exp(1)` and `StrictMath.exp(1)` only check six decimal digits of display output, **without claiming every bit of the two values must match**. Using small numbers, zero, and special values helps build more stable tests than checking every exact digit of a transcendental calculation across all JVMs.

## 12. Designing Tests According to Javadoc Instead of Hard-Coding Current Machine Results

A test suite should separate three categories:

**(A) Special cases with deterministic results:** check `Double.isNaN(Math.sqrt(-1.0))`, `Math.pow(Double.NaN, 0.0) == 1.0`, or the negative-zero bit after `Math.sqrt(-0.0)`. For NaN, never use `== Double.NaN`.

**(B) Input domain and output values:** verify whether the application rejects logs of non-positive numbers, or detects overflow to infinity. These rules belong to the **business contract**, supplementing Javadoc.

**(C) Error bounds of finite results:** if a method only promises "within 1 ulp" rather than identical bits, do not save an overly long decimal string from the current machine as the sole expected value across all systems. Compare against a sufficiently accurate reference using spec-compliant error bounds, while also accounting for subnormals, infinity, NaN, and signed zero. A formula like `abs(actual - expected) <= Math.ulp(actual)` is only a **rough illustration**—it may not measure exact ULP of the true result, does not handle special values, and **does not replace standard verification procedures**.

For instance, a test for the increasing behavior on the positive log domain can check multiple sample points. Yet a few sample points **do not fully prove** semi-monotonicity for every `double`. Thorough testing requires knowing the exact Javadoc contract, reference datasets, input ranges, and numerical evaluation tools.

If a system demands bit-for-bit results for reproducibility, consider `StrictMath` for fdlibm-bound functions and document version/input policies explicitly, rather than accidentally relying on one specific `Math` implementation.

## 13. Common Misconceptions and Checklist

| Misconception | Correct Understanding |
| --- | --- |
| "`Math` functions receiving out-of-domain numbers throw `ArithmeticException`." | Many floating-point functions return `NaN` or Infinity, per each special case. |
| "Any NaN input must yield NaN." | False for cases like `Math.pow(NaN,0.0)` and `hypot(Infinity,NaN)`. |
| "`sqrt(-0.0)` must yield NaN because it's negative." | False: -0.0 preserves its sign under the square root contract. |
| "`Math.min(+0.0,-0.0)` can arbitrarily pick either zero." | Javadoc specifies returning -0.0; `max` returns +0.0. |
| "1 ulp means an error of at most 1.0." | False: ulp is one step of the binary floating-point grid at the result's magnitude. |
| "Within 1 ulp means the result is correctly rounded." | Not necessarily; an adjacent value may be chosen instead of the nearest one. |
| "`Math.sqrt`, `Math.exp`, and `Math.atan2` share the same error guarantee." | No: read each Javadoc entry individually. |
| "Semi-monotonic means `sin` always increases." | False: it is a constraint preserving direction on intervals where the mathematical function is monotonic. |
| "`StrictMath` always has more accurate digits than `Math`." | There is no such guarantee; the focus is reproducibility via specified algorithms. |
| "Java 17 always-strict makes `Math` and `StrictMath` identical." | False: expression semantics do not erase specification differences in library methods. |
| "`Math.abs(int)` is always non-negative." | False for `Integer.MIN_VALUE`; `absExact` can be used to detect overflow. |
| "`Double.isFinite` suffices to prove a result has no error." | False: it only excludes NaN/Infinity, without checking rounding or underflow. |

Practical checklist:

1. **Open the Javadoc for the exact Java version in use**, locating the exact overload by parameter types.
2. **Read the formula and real domain**, but do not stop there.
3. **Read the entire "Special Cases" section**: NaN, Infinity, signed zero, boundary parameters, and precedence among cases.
4. **Read the accuracy guarantee line** for each method: correctly rounded, 1 ulp, 2 ulp, 2.5 ulp, and semi-monotonic if applicable.
5. **Distinguish `Math` and `StrictMath` by reproducibility needs**, not by guessing from the class name.
6. **Define the business contract** on whether NaN/infinite results, signed zero, and underflow are permitted.
7. **Test boundary cases separately from accuracy tests**; do not use a single `==` comparison for all floating-point numbers.
8. **When strict accuracy or reproducibility is needed**, use reference data and proper error criteria instead of treating the current machine's output as universal truth across all platforms.

**Conclusion:** The `Math`/`StrictMath` contract is more than just formulas. It encompasses **domains, special cases, ULP-measured accuracy, approximate monotonicity, and reproducibility levels**. Writing correct Java code requires reading **each method's Javadoc**, validating values for the application's intent, and testing what the API actually guarantees.
