# `copySign`, `scalb`, and `getExponent` in Java: Sign, Powers of 2, and IEEE 754 Exponents

`java.lang.Math` and `java.lang.StrictMath` contain three groups of methods that frequently appear when working **close to the binary representation of `float`/`double`**:

- **`copySign(magnitude, sign)`**: takes the magnitude of the first argument while attaching the **sign of the second argument**, including the sign of negative zero.
- **`scalb(value, scaleFactor)`**: multiplies the value by **\(2^{scaleFactor}\)** according to floating-point rounding rules, very useful when adjusting binary scale.
- **`getExponent(value)`**: returns the **unbiased exponent of the exponent field** in floating-point representation, while defining specific sentinel values for zero, subnormal, NaN, and infinity.

```java
double signed = Math.copySign(3.5, -0.0); // -3.5
double scaled = Math.scalb(1.5, 3);       // 12.0 = 1.5 × 2^3
int exponent = Math.getExponent(8.0);     // 3
```

These three functions are **not interchangeable**: `copySign` modifies the sign bit while keeping magnitude; `scalb` changes magnitude scale and can overflow/underflow; `getExponent` inspects exponent information **rather than computing a general logarithm**. This lesson focuses on Java 17+ semantics, special IEEE 754 values, runnable examples, and safe usage.

## 1. Recap of the `float` and `double` Representation Model

Java's two core floating-point types use the IEEE 754 binary format. A non-zero finite **normal** number is represented by a sign bit, a biased exponent, and a fraction; conceptually taking the form:

\[
(-1)^{sign}\times (1.fraction)_2 \times 2^{exponent}
\]

| Component | `float` / binary32 | `double` / binary64 |
| --- | ---: | ---: |
| Total bits | 32 | 64 |
| Sign bit | 1 | 1 |
| Exponent bits | 8 | 11 |
| Fraction bits | 23 | 52 |
| Minimum **normal** exponent | `Float.MIN_EXPONENT = -126` | `Double.MIN_EXPONENT = -1022` |
| Maximum **normal** exponent | `Float.MAX_EXPONENT = 127` | `Double.MAX_EXPONENT = 1023` |
| Smallest positive finite **normal** | `Float.MIN_NORMAL` | `Double.MIN_NORMAL` |
| Smallest positive number, including **subnormal** | `Float.MIN_VALUE` | `Double.MIN_VALUE` |

**Subnormal** numbers have an exponent field of 0 and do not use an implicit leading 1 bit in the significand like normal numbers. Thanks to subnormals, Java can represent positive numbers smaller than `MIN_NORMAL`, with gradually decreasing precision.

In addition to finite numbers, there are `+0.0`, `-0.0`, `+Infinity`, `-Infinity`, and **NaN**. These values require special rules for functions manipulating sign, scale, or exponent.

**Misconception to avoid:** `Double.MIN_VALUE` is the **smallest positive subnormal number**, **not the most negative `double`**. Similarly, `Math.getExponent(Double.MIN_VALUE)` does not return the mathematical exponent `-1074` of that specific subnormal value; it returns a sentinel per the API rules.

## 2. `Math.copySign`: Taking Magnitude from One Number and Sign from Another

Overload signatures:

```java
static double Math.copySign(double magnitude, double sign)
static float Math.copySign(float magnitude, float sign)
```

Corresponding methods exist in `StrictMath`. Both arguments must match the `double` or `float` overload; the method creates no wrapper objects and parses no text strings.

Example:

```java
Math.copySign(3.5, -2.0);        // -3.5
Math.copySign(-3.5, 2.0);        // 3.5
Math.copySign(0.0, -1.0);        // -0.0
Math.copySign(-0.0, +1.0);       // +0.0
Math.copySign(Double.POSITIVE_INFINITY, -1.0);
// -Infinity
```

The first argument supplies the **magnitude**. If it is already negative, `copySign` can make it positive when the second argument carries a positive sign. This is neither adding two values, taking a product, nor checking `sign > 0`.

### Sign of `-0.0`: Why Is `sign < 0` Not Enough?

In primitive floating-point comparisons:

```java
-0.0 == +0.0      // true
-0.0 < 0.0        // false
```

Yet they have **different sign bits**. `Math.copySign(3.5, -0.0)` returns **`-3.5`**, because it reads the **sign of negative zero**, rather than testing `-0.0 < 0`. Similarly:

```java
double negativeZero = Math.copySign(0.0, -1.0);
boolean sameValue = negativeZero == 0.0; // true
long rawBits = Double.doubleToRawLongBits(negativeZero);
// 0x8000000000000000L
```

If business logic needs to detect negative zero, inspect the sign bit using `Double.doubleToRawLongBits` or observe whether `1.0 / negativeZero` is `-Infinity`. Do not use `value < 0` as a general way to detect the sign bit.

### Sign of Infinity

`copySign` preserves infinite magnitude and changes the sign:

```java
double result = Math.copySign(
    Double.POSITIVE_INFINITY, -1.0
);
// -Infinity
```

If `magnitude` is `0.0`, the function still returns zero with the corresponding sign; if `magnitude` is infinite, it returns infinity with the same sign as `sign`.

### `NaN` Cases and Differences with `StrictMath`

**Important regarding Java 17 specification:** When the **`sign` argument is NaN**, `StrictMath.copySign` **always treats that NaN as having a positive sign**. Meanwhile, `Math.copySign` is **not required** to treat every NaN sign as positive; implementations are permitted to use the sign bit of certain NaN patterns for optimization.

Therefore, do not write business logic relying on the sign of `NaN` expecting `Math.copySign` and `StrictMath.copySign` to return identical results on every JVM.

If `magnitude` is NaN, the result remains NaN; **do not use this operation as a protocol for preserving every NaN payload bit**. If you truly need to preserve every input/output bit pattern (including signaling NaNs), work with `int`/`long` bit patterns or raw bytes, because passing a signaling NaN through floating-point values can quiet it.

**When to use `copySign`?** For example, constructing a result from a known magnitude while preserving the sign of the original element, retaining signed zero in floating-point processing, or performing intentional representation transforms. It is not for "normalizing values" while ignoring NaN.

## 3. `Math.scalb`: Exact Multiplication by a Power of 2 When Representable

Signatures:

```java
static double Math.scalb(double value, int scaleFactor)
static float Math.scalb(float value, int scaleFactor)
```

The method computes the mathematical meaning **\(value\times 2^{scaleFactor}\)** and returns a floating-point result under defined rounding rules. Example:

```java
Math.scalb(1.5, 3);   // 12.0
Math.scalb(3.0, -1);  // 1.5
Math.scalb(1.0, 10);  // 1024.0
Math.scalb(0.5f, 2);  // 2.0f
```

Unlike multiplying by an arbitrary `double`, multiplying by a power of 2 essentially **shifts the exponent scale in binary**. For suitable normal inputs where the result remains in the representable normal range, scaling can be exact. This is why `scalb` is useful in numerical algorithms or binary rescaling.

However, **do not claim every `scalb` never rounds**:

- When the result is **subnormal**, precision bits in the significand can be lost.
- When the result is too large, it can **overflow to `±Infinity`**.
- When the result is too small, it can **underflow to `±0.0`**, still preserving the sign.
- NaN remains NaN; ±Infinity remains infinity with the same sign; zero remains zero with the same sign.

`scalb` performs scaling as a floating-point arithmetic function; **do not alter bits by manually adding directly to the raw exponent**, which easily breaks on subnormals, NaN, Infinity, and overflow.

### Why Not Always Write `x * Math.pow(2, n)`?

The mathematical formula is identical, yet:

```java
double a = Math.scalb(x, n);
// double b = x * Math.pow(2.0, n);
```

The second line creates an **intermediate result `Math.pow(2.0, n)`** that can overflow or underflow before multiplying by `x`, and may round at different points. `Math.scalb` aims to perform power-of-2 scaling with its own result specification, avoiding building an unnecessary intermediate factor.

For instance, if `x` is very small while `2^n` is large beyond the `double` range, `Math.pow(2, n)` can become Infinity even though the ideal product is still finite. `Math.scalb(x, n)` is the better tool when this is genuinely a base-2 scaling operation.

Do not confuse `scalb` with `Math.pow(value, exponent)`: `scalb(value, n)` multiplies `value` by `2^n`, **not** `value^n`.

## 4. Extreme Magnitudes: Overflow, Underflow, and Subnormals

In Java, a `double` has a maximum normal exponent of 1023. Scaling up too much can produce infinity:

```java
Math.scalb(Double.MAX_VALUE, 1);
// Infinity
```

At the small end, `Double.MIN_VALUE` is the smallest positive subnormal:

```java
Math.scalb(Double.MIN_VALUE, -1); // 0.0 (underflow)
```

When a small value is given a negative sign and scaled down further, the sign can persist in negative zero:

```java
double x = Math.scalb(-Double.MIN_VALUE, -1);
// -0.0; raw bits 0x8000000000000000
```

**Subnormals are not always equal to zero.** Example:

```java
double half = Math.scalb(Double.MIN_NORMAL, -1);
// Positive subnormal number, bit pattern 0x0008000000000000L
```

It is smaller than `Double.MIN_NORMAL` yet non-zero. This helps explain why `getExponent` in the next section returns **the same sentinel** for many vastly different subnormal values, rather than each value's individual mathematical exponent.

**Do not use `scalb` to skip domain checks:** If inputs can be NaN/Infinity or scale factors are huge, establish a validation policy. If computations require finite results, check `Double.isFinite(result)` (or `Float.isFinite`) after scaling and assess whether underflow to zero constitutes a business error.

### Sign of Zero When Scaling

`Math.scalb(-0.0, 1000)` still yields **`-0.0`**. There is nothing to scale up into a non-zero number: scaling conceptually multiplies zero by a positive power-of-2 factor, leaving the zero sign bit unchanged.

The method does not mutate the original argument, has no side effects on `double` variables, and allocates no wrapper objects to return primitives.

## 5. `Math.getExponent`: Inspecting the Unbiased Exponent Field

Signatures:

```java
static int Math.getExponent(double value)
static int Math.getExponent(float value)
```

The return type is **`int`**, representing the unbiased exponent related to the IEEE 754 exponent field. For a **non-zero finite normal** number, the result can be understood as the exponent `e` such that the magnitude lies in:

\[
2^e \le |value| < 2^{e+1}
\]

Example:

```java
Math.getExponent(8.0);   // 3, since 8 = 1 × 2^3
Math.getExponent(0.75);  // -1, since 0.75 = 1.5 × 2^-1
Math.getExponent(-16.0); // 4; sign does not change exponent
```

**However, for zero, subnormals, NaN, or infinity, `getExponent` returns an API-defined sentinel rather than computing `floor(log2(abs(value)))` mathematically.**

### `double` Results Table

| Argument | `Math.getExponent(double)` | Explanation |
| --- | ---: | --- |
| `8.0` | `3` | Normal, exponent 3 |
| `0.75` | `-1` | Normal, 0.75 = 1.5 × 2^-1 |
| `Double.MIN_NORMAL` | `-1022` | Smallest normal |
| `Double.MAX_VALUE` | `1023` | Largest normal |
| `+0.0` or `-0.0` | `-1023` | `Double.MIN_EXPONENT - 1` |
| `Double.MIN_VALUE` (subnormal) | `-1023` | Same sentinel for all subnormals |
| `Double.NaN` | `1024` | `Double.MAX_EXPONENT + 1` |
| `±Infinity` | `1024` | Same sentinel as NaN |

For `float`, the two corresponding sentinel values are:

- Zero and subnormal: **`Float.MIN_EXPONENT - 1 = -127`**.
- NaN and ±Infinity: **`Float.MAX_EXPONENT + 1 = 128`**.

Example:

```java
Math.getExponent(0.0f);                      // -127
Math.getExponent(Float.MIN_VALUE);           // -127
Math.getExponent(Float.MIN_NORMAL);          // -126
Math.getExponent(Float.POSITIVE_INFINITY);   // 128
```

`Float.MIN_VALUE` has a mathematical value of `2^-149`, yet `Math.getExponent(Float.MIN_VALUE)` still returns `-127`. `Double.MIN_VALUE` has a mathematical value of `2^-1074`, yet `Math.getExponent(Double.MIN_VALUE)` still returns `-1023`. **Do not read sentinel results as the log2 of a subnormal.**

## 6. Why Cannot `getExponent` Replace `log2`?

Within the normal domain, the exponent result tells you the **base-2 order of magnitude**. However:

- `getExponent(8.0)` is 3, without returning the fraction/mantissa.
- `getExponent(12.0)` is also 3 because `12 = 1.5 × 2^3`.
- `getExponent(0.0)` is `-1023`; not the logarithm of zero.
- `getExponent(Double.MIN_VALUE)` is `-1023`; whereas its mathematical power-of-2 exponent is `-1074`.
- `getExponent(Double.NaN)` and `getExponent(Double.POSITIVE_INFINITY)` are both 1024; the sentinel number does not tell whether the argument is NaN or infinity.

If you need the real logarithm of a positive finite value, consider `Math.log(value) / Math.log(2.0)` (subject to floating-point error), but **do not treat it as a bit-exact replacement for `getExponent`**. For raw exponent decoding and deep subnormal handling, understand the format and build a dedicated algorithm.

### How to Distinguish Special Cases?

```java
double x = Double.MIN_VALUE;
int e = Math.getExponent(x);

if (Double.isNaN(x)) {
    // NaN: do not use e as the exponent of a finite number
} else if (Double.isInfinite(x)) {
    // Infinity
} else if (x == 0.0) {
    // +0.0 or -0.0
} else if (e == Double.MIN_EXPONENT - 1) {
    // x is a non-zero subnormal
} else {
    // x is a non-zero finite normal number
}
```

This is an **illustrative code snippet** and must be placed inside a method/class when used. The check order is intentional: `e == Double.MIN_EXPONENT - 1` by itself **does not distinguish** zero from subnormals; `e == Double.MAX_EXPONENT + 1` by itself **does not distinguish** NaN from infinity.

The checks above suit algorithms that need to separate normal/subnormal cases. Many ordinary applications only need `Double.isFinite`, zero checks, and input validation, without bit-level exponent manipulation.

## 7. Combining the Three Functions Without Distorting Semantics

The three APIs are very useful for algorithms handling **separate sign**, **separate scale**, and **separate exponent**.

Example of a conceptual pipeline:

```java
double input = -12.0;
int e = Math.getExponent(input);     // 3
double base = Math.scalb(input, -e); // -1.5
double positiveBase = Math.copySign(base, +1.0); // 1.5
```

For non-zero finite normal numbers, `base` generally has a magnitude from `1` up to under `2`, because we divide the value by `2^e`. `copySign` then converts it to a positive magnitude using sign-bit semantics.

**Caveat:** Do not apply the "normalization" pipeline above to every value:

- `input == 0.0`: `getExponent` returns a sentinel, not a useful exponent to normalize zero.
- `input` subnormal: `getExponent`'s sentinel is not each value's true exponent; `scalb(input, -e)` is not guaranteed to produce a normalized mantissa as desired.
- `input` NaN/Infinity: must be handled separately, otherwise the normalized result does not represent a finite number.
- Scaling can overflow/underflow or lose precision at extreme values.

If an algorithm requires more exact floating-point normalization, establish domain rules and dedicated test suites rather than intuitively chaining the three functions.

## 8. `Math` vs. `StrictMath`: Practical Differences

Both classes provide `copySign`, `scalb`, and `getExponent` overloads for `float`/`double` respectively. They are **static methods**; do not instantiate `Math` or `StrictMath`.

| Aspect | `Math` | `StrictMath` |
| --- | --- | --- |
| `copySign` with finite sign (including zero) | Takes sign bit from `sign` argument | Same semantics |
| `copySign` when **`sign` is NaN** | Allowed not to always treat NaN as positive | **Required to treat NaN sign as positive** |
| `scalb` | Multiplies by power of 2 per scale/rounding spec | Same arithmetic spec for corresponding function |
| `getExponent` | Returns unbiased exponent and sentinels | Same sentinel table |
| Return types | `copySign/scalb`: `float` or `double`; `getExponent`: `int` | Corresponding |

Do not infer from the name `StrictMath` that every method in this class always produces a different value from `Math`. In ordinary finite cases, results are usually identical. The specific, important difference in this lesson's API group is **handling a NaN `sign` argument in `copySign`** as specified in the Java documentation.

When predictable behavior for NaN sign per the API is needed, use `StrictMath.copySign` and define NaN-handling rules upfront in the design. When parameters are appropriate finite values, `Math` is usually the convenient direct API.

## 9. Complete Java 17+ Program for Self-Verification

Create file `FloatingScaleDemo.java`:

```java
public class FloatingScaleDemo {
    static String hex(double x) {
        return String.format("%016x", Double.doubleToRawLongBits(x));
    }

    public static void main(String[] args) {
        System.out.println("copySign(3.5, -0.0): "
            + Math.copySign(3.5, -0.0));
        System.out.println("copySign(-3.5, +0.0): "
            + Math.copySign(-3.5, +0.0));
        System.out.println("copySign(infinity, -1): "
            + Math.copySign(Double.POSITIVE_INFINITY, -1.0));
        System.out.println("copySign(+0.0, -1.0) raw: "
            + hex(Math.copySign(0.0, -1.0)));
        System.out.println("float copySign: "
            + Math.copySign(2.5f, -0.0f));
        System.out.println("strict copySign: "
            + StrictMath.copySign(3.5, -1.0));

        System.out.println("scalb(1.5,3): " + Math.scalb(1.5, 3));
        System.out.println("scalb(3,-1): " + Math.scalb(3.0, -1));
        System.out.println("scalb zero raw: "
            + hex(Math.scalb(-0.0, 1000)));
        System.out.println("scalb underflow: "
            + Math.scalb(Double.MIN_VALUE, -1));
        System.out.println("scalb negative underflow raw: "
            + hex(Math.scalb(-Double.MIN_VALUE, -1)));
        System.out.println("scalb overflow: "
            + Math.scalb(Double.MAX_VALUE, 1));
        System.out.println("scalb min-normal/2 raw: "
            + hex(Math.scalb(Double.MIN_NORMAL, -1)));
        System.out.println("strict scalb: "
            + StrictMath.scalb(1.5, 3));

        System.out.println("exp(8.0): " + Math.getExponent(8.0));
        System.out.println("exp(0.75): " + Math.getExponent(0.75));
        System.out.println("exp(0.0): " + Math.getExponent(0.0));
        System.out.println("exp(min subnormal): "
            + Math.getExponent(Double.MIN_VALUE));
        System.out.println("exp(min normal): "
            + Math.getExponent(Double.MIN_NORMAL));
        System.out.println("exp(max): "
            + Math.getExponent(Double.MAX_VALUE));
        System.out.println("exp(NaN): "
            + Math.getExponent(Double.NaN));
        System.out.println("exp(infinity): "
            + Math.getExponent(Double.POSITIVE_INFINITY));

        System.out.println("float exp(zero): "
            + Math.getExponent(0.0f));
        System.out.println("float exp(min normal): "
            + Math.getExponent(Float.MIN_NORMAL));
        System.out.println("float exp(infinity): "
            + Math.getExponent(Float.POSITIVE_INFINITY));
        System.out.println("strict getExponent: "
            + StrictMath.getExponent(8.0));
    }
}
```

Compile and run:

```bash
javac FloatingScaleDemo.java
java FloatingScaleDemo
```

Stdout from the program (verified against JDK):

```text
copySign(3.5, -0.0): -3.5
copySign(-3.5, +0.0): 3.5
copySign(infinity, -1): -Infinity
copySign(+0.0, -1.0) raw: 8000000000000000
float copySign: -2.5
strict copySign: -3.5
scalb(1.5,3): 12.0
scalb(3,-1): 1.5
scalb zero raw: 8000000000000000
scalb underflow: 0.0
scalb negative underflow raw: 8000000000000000
scalb overflow: Infinity
scalb min-normal/2 raw: 0008000000000000
strict scalb: 12.0
exp(8.0): 3
exp(0.75): -1
exp(0.0): -1023
exp(min subnormal): -1023
exp(min normal): -1022
exp(max): 1023
exp(NaN): 1024
exp(infinity): 1024
float exp(zero): -127
float exp(min normal): -126
float exp(infinity): 128
strict getExponent: 3
```

**Guide to reading the output:**

- The six `copySign` lines show that the sign of negative zero matters, even when its value compares equal to positive zero. `StrictMath` returns the same result on ordinary arguments.
- The eight `scalb` lines demonstrate scaling powers of 2 up/down, zero sign, overflow to infinity, and underflow to zero/subnormal.
- The `getExponent` lines distinguish normals from sentinels: `double` zero/subnormal is `-1023`, NaN/infinity is `1024`; `float` is `-127` and `128` respectively.
- The `hex` helper uses **raw bit patterns** to distinguish negative/positive zero; hex output is padded to 16 characters for `double`.

## 10. When Should You Use These Three APIs?

| Need | API to Choose | Notes |
| --- | --- | --- |
| Attach sign from a reference value | `Math.copySign` | Also reads the sign of `-0.0` |
| Require NaN sign to always be treated as positive | `StrictMath.copySign` | Differs from `Math.copySign` contract on NaN sign |
| Multiply/divide by a power of 2 | `Math.scalb` | Watch for overflow/underflow |
| Adjust scale for a `float` number | `Math.scalb(float, int)` | Result remains `float` |
| Inspect exponent order of a normal number | `Math.getExponent` | Not a general logarithm |
| Classify zero/subnormal/special | `getExponent` combined with `isNaN`/`isInfinite`/zero check | Sentinel alone is insufficient |
| Inspect true bit pattern | `Double.doubleToRawLongBits`/`Float.floatToRawIntBits` | Do not confuse bit-inspection APIs with numeric scaling |
| Check for finite value | `Double.isFinite`/`Float.isFinite` | Must be used explicitly if contract requires |

Scientific data processing, number representation in normalization algorithms, signal decoding, or statistics spanning wide magnitude ranges often need these functions. However, do not use them thinking low-level functions are always "more accurate": **the choice stems from the desired operation and representation limits**.

## 11. Common Misconceptions

1. **"`copySign(x, y)` computes `x * y`."** False: it takes the magnitude of `x` and the sign of `y`.
2. **"`copySign` with `-0.0` is the same as positive sign because `-0.0 == 0.0`."** False: the sign bit is preserved and applied.
3. **"`Math.copySign` and `StrictMath.copySign` have identical contracts for NaN sign."** False: `StrictMath` treats NaN sign as positive; `Math` is allowed to differ.
4. **"`scalb(x, n)` is `Math.pow(x, n)`."** False: `scalb` computes `x × 2^n`.
5. **"`scalb` is always exact to every bit, even for subnormals."** False: underflow/rounding can lose precision or produce zero.
6. **"Computing `x * Math.pow(2,n)` is always equivalently safe to `scalb`."** False: the expression's intermediate result can overflow/underflow before multiplying.
7. **"`getExponent(x)` always returns `floor(log2(abs(x)))`."** False for zero, subnormals, NaN, and Infinity.
8. **"`Math.getExponent(Double.MIN_VALUE) == -1074`."** False: the API returns `-1023` for all `double` subnormals.
9. **"`Math.getExponent(0.0)` and `Math.getExponent(Double.MIN_VALUE)` differ."** False: both are `-1023`.
10. **"`getExponent` returns `Double.MIN_EXPONENT` for zero."** False: it returns `Double.MIN_EXPONENT - 1`.
11. **"`getExponent` returns NaN if input is NaN."** False: the return type is `int` and it returns the sentinel `MAX_EXPONENT + 1`.
12. **"`getExponent` distinguishes NaN from infinity from its return value alone."** False: they share the same sentinel.
13. **"`Double.MIN_VALUE` is the smallest negative value of `double`."** False: it is the smallest positive subnormal number.
14. **"`scalb(-0.0, k)` becomes `+0.0` because it multiplies by a positive power of 2."** False: the sign of zero is preserved.
15. **"`copySign` can replace every sign-flip operation on NaN while preserving payload."** False: do not treat it as a bit-perfect protocol for all NaN forms.

## 12. Self-Check

**1. What does `Math.copySign(5.0, -0.0)` return?** → `-5.0`, because `-0.0` carries a negative sign.

**2. What does `Math.copySign(-5.0, +0.0)` return?** → `5.0`, because magnitude 5 takes the new positive sign.

**3. What does `Math.scalb(1.25, 3)` return?** → `10.0`, from `1.25 × 2^3`.

**4. What does `Math.scalb(3.0, -1)` return?** → `1.5`.

**5. What does `Math.scalb(Double.MAX_VALUE, 1)` return?** → `Infinity` due to overflow.

**6. What sign does `Math.scalb(-Double.MIN_VALUE, -1)` have?** → `-0.0`; the negative sign bit is preserved.

**7. What is `Math.getExponent(0.75)`?** → `-1`.

**8. Are `Math.getExponent(Double.MIN_NORMAL)` and `Math.getExponent(Double.MIN_VALUE)` equal?** → No: `-1022` and `-1023` respectively.

**9. How does `Math.getExponent(Double.NaN)` compare to `Math.getExponent(Double.POSITIVE_INFINITY)`?** → Both are `1024`, so a separate classification API must be used to distinguish them.

**10. Is `Math.getExponent(Float.MIN_VALUE)` equal to `-149`?** → No: it returns the `-127` sentinel for subnormals.

**11. What differs between `Math.copySign` and `StrictMath.copySign` if `sign` is NaN?** → `StrictMath` always treats NaN sign as positive; `Math` is permitted to handle the sign of some NaNs differently by implementation.

**Key takeaway:** `copySign` works on **sign bits**; `scalb` changes **power-of-2 scale** with rounding/overflow/underflow rules; `getExponent` reads the **unbiased exponent** of the representation and returns sentinels for **zero, subnormal, NaN, and infinity**. When used in algorithms, classify special values, preserve proper `float`/`double` types, and do not confuse bit-level results with logarithms or infinite-precision arithmetic.
