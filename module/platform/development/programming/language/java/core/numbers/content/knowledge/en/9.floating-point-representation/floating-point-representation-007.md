# MIN_VALUE, MIN_NORMAL, and MAX_VALUE of float/double in Java

> **Java core – numbers · Floating-Point Representation**  
> **Objective:** Distinguish the three key boundary constants of `Float`/`Double`, accurately read the IEEE 754 *normal* and *subnormal* ranges, understand underflow/overflow, recognize signed zero, and choose appropriate boundary checks in Java 17+.

## 1. The Most Important Answer

For **`float` and `double`**, Java defines:

- **`MIN_VALUE`:** the **smallest nonzero finite positive** representable floating-point number, lying in the **subnormal** region.
- **`MIN_NORMAL`:** the **smallest positive normal** finite floating-point number.
- **`MAX_VALUE`:** the **largest finite positive** representable floating-point number.

**Warning:** `Double.MIN_VALUE` is **not the smallest negative number**. This constant is greater than 0, yet extremely close to 0. If you need the finite negative `double` value with the largest magnitude, use `-Double.MAX_VALUE`. The same rule applies to `Float`.

This differs completely from `Integer.MIN_VALUE` or `Long.MIN_VALUE`: for **integer** types, `MIN_VALUE` is the most negative number; for **floating-point** types, it is the **smallest nonzero positive** number.

## 2. Table of Key Values

| Constant | Java Decimal Print Value | Exact Base-2 Form |
| --- | --- | --- |
| `Float.MIN_VALUE` | `1.4E-45` | `2^-149` |
| `Float.MIN_NORMAL` | `1.17549435E-38` | `2^-126` |
| `Float.MAX_VALUE` | `3.4028235E38` | `(2 - 2^-23) × 2^127` |
| `Double.MIN_VALUE` | `4.9E-324` | `2^-1074` |
| `Double.MIN_NORMAL` | `2.2250738585072014E-308` | `2^-1022` |
| `Double.MAX_VALUE` | `1.7976931348623157E308` | `(2 - 2^-52) × 2^1023` |

The decimal strings in the table are how Java displays the values as short strings sufficient to identify the binary values; do not interpret `4.9E-324` as mathematically equal to `4.9 × 10^-324`. The power-of-2 form directly describes the value in binary.

These constants live in `java.lang.Float` and `java.lang.Double`; no separate import is needed.

```java
float smallestPositiveFloat = Float.MIN_VALUE;
float smallestNormalFloat = Float.MIN_NORMAL;
float largestFiniteFloat = Float.MAX_VALUE;

double smallestPositiveDouble = Double.MIN_VALUE;
double smallestNormalDouble = Double.MIN_NORMAL;
double largestFiniteDouble = Double.MAX_VALUE;
```

All six constants hold **positive, finite, nonzero** values. None of them is `NaN` or infinity.

## 3. IEEE 754 Layout Explains the Three Boundaries

Java uses IEEE 754 binary formats for `float` (*binary32*) and `double` (*binary64*):

| Property | `float` | `double` |
| --- | ---: | ---: |
| Total bits | 32 | 64 |
| Sign bit | 1 | 1 |
| Stored exponent bits | 8 | 11 |
| Stored fraction bits | 23 | 52 |
| Effective precision bits of normal numbers | 24 | 53 |
| Smallest unbiased normal exponent | −126 | −1022 |
| Largest unbiased normal exponent | +127 | +1023 |

Diagram:

```text
float  (32 bits): [sign:1][exponent:8 ][fraction:23]
double (64 bits): [sign:1][exponent:11][fraction:52]
```

For a **finite normal** number whose exponent field is neither all 0s nor all 1s, the magnitude has the form:

\[
(1+\mathrm{fraction})\times 2^e
\]

The leading `1` bit of the normal significand is **implicit** (*implicit leading 1*), so the effective precision has 1 more bit than the fraction bits stored in memory.

For a **subnormal** number, the exponent field is **all 0s**, the fraction field is **nonzero**, and the leading bit becomes **0**:

\[
\mathrm{fraction}\times 2^{e_{\min}}
\]

Here `fraction` is the value from the binary fraction bits; `e_min` is −126 for `float` and −1022 for `double`. Without the implicit `1` bit, the relative precision of subnormal numbers decreases gradually as values approach 0.

An exponent field of **all 1s** is reserved for special values: `Infinity` and `NaN`. Zero has both the exponent field and fraction field equal to 0, with a sign bit of either 0 or 1.

## 4. MIN_NORMAL: The Starting Boundary of Normal Numbers

The smallest positive normal number has an effective significand of **1.0** and the smallest normal exponent:

\[
\mathrm{Float.MIN\_NORMAL}=1.0\times 2^{-126}
\]

\[
\mathrm{Double.MIN\_NORMAL}=1.0\times 2^{-1022}
\]

In Java:

```java
float f = 0x1.0p-126f;
double d = 0x1.0p-1022;

System.out.println(f == Float.MIN_NORMAL);   // true
System.out.println(d == Double.MIN_NORMAL); // true
```

These hex literals read as: significand `0x1.0` equal to 1, `p` indicating the power of **2**, and the `f` suffix forcing type `float`. Hex expressions are very convenient for expressing exact binary boundaries.

**Pitfall to avoid:** `MIN_NORMAL` is not the smallest nonzero positive number. Java can represent even smaller values thanks to the subnormal range.

## 5. MIN_VALUE: The Smallest Nonzero Step Near Zero

The smallest positive subnormal number has **only the lowest fraction bit equal to 1**. Its value is:

\[
\mathrm{Float.MIN\_VALUE}=2^{-149}
\]

\[
\mathrm{Double.MIN\_VALUE}=2^{-1074}
\]

It can be written exactly as:

```java
float minFloat = 0x1p-149f;       // Float.MIN_VALUE
double minDouble = 0x1p-1074;   // Double.MIN_VALUE

System.out.println(minFloat == Float.MIN_VALUE);   // true
System.out.println(minDouble == Double.MIN_VALUE); // true
```

For `double`, the fraction field has 52 bits, so stepping from exponent −1022 down to the last fraction bit takes 52 more powers: `−1022 − 52 = −1074`. For `float`: `−126 − 23 = −149`.

The interval between **0** and **MIN_NORMAL** contains many positive subnormals:

```text
0       MIN_VALUE      ...     largest subnormal     MIN_NORMAL
|-----------|--------------------------|------------------|
            ^                                      ^
  smallest positive subnormal               smallest positive normal
```

The spacing between two consecutive positive subnormals equals `MIN_VALUE` of the respective type. This is the *gradual underflow* mechanism, helping avoid abruptly truncating very small calculations straight to 0.

A verification check:

```java
double smallestStep = Double.MIN_VALUE;
double largestSubnormal = Math.nextDown(Double.MIN_NORMAL);

System.out.println(largestSubnormal + smallestStep
        == Double.MIN_NORMAL); // true
```

The largest subnormal value is the number immediately preceding `MIN_NORMAL` on the positive number line.

## 6. MAX_VALUE: Largest Finite Number, Not Yet Infinity

`Float.MAX_VALUE` and `Double.MAX_VALUE` carry the **largest finite exponent** and all fraction bits set to 1:

\[
\mathrm{Float.MAX\_VALUE}=(2-2^{-23})\times 2^{127}
\]

\[
\mathrm{Double.MAX\_VALUE}=(2-2^{-52})\times 2^{1023}
\]

Exact hex literal form:

```java
float largestFloat = 0x1.fffffep127f;
double largestDouble = 0x1.fffffffffffffp1023;

System.out.println(largestFloat == Float.MAX_VALUE); // true
System.out.println(largestDouble == Double.MAX_VALUE); // true
```

**MAX_VALUE is not Infinity.** It is finite. However, an operation exceeding the range can **overflow to infinity**:

```java
double big = Double.MAX_VALUE;
double overflow = big * 2.0;

System.out.println(Double.isFinite(big)); // true
System.out.println(overflow);             // Infinity
System.out.println(Double.isInfinite(overflow)); // true
```

Do not assume every near-boundary excess immediately produces `Infinity`: IEEE 754 rounds results; for some mathematical real values slightly larger than `MAX_VALUE`, rounding can still return `MAX_VALUE`. What is accurate to remember is that when the **rounded result exceeds the largest representable finite number**, it becomes infinity under floating-point rules.

For negative results exceeding the finite lower bound, you can get `Double.NEGATIVE_INFINITY`. The constants `POSITIVE_INFINITY`/`NEGATIVE_INFINITY` and `NaN` belong to the special-value system, distinct from `MAX_VALUE`.

## 7. Number Line Regions: Negative, 0, Subnormal, Normal

Considering finite `double` values alone:

```text
   -Double.MAX_VALUE                                  Double.MAX_VALUE
          |                                                   |
    neg. normal ... neg. subnormal  -0.0  +0.0  pos. subnormal ... normal
          |                    |    |    |                   |
          +--------------------+----+----+-------------------+

Positive boundaries:
0 < Double.MIN_VALUE < Double.MIN_NORMAL < Double.MAX_VALUE
```

The two numbers `+0.0` and `-0.0` have **different sign bits** yet compare equal with the `==` operator:

```java
System.out.println(0.0 == -0.0); // true
System.out.println(1.0 / 0.0);   // Infinity
System.out.println(1.0 / -0.0);  // -Infinity
```

So `-0.0` is an important value right at the 0 boundary, yet it **cannot be called** the “smallest finite negative number” in terms of value range; the finite negative number with the largest magnitude is `-Double.MAX_VALUE`.

A **finite** value ordering around 0:

```text
... < -Double.MIN_NORMAL < -Double.MIN_VALUE < -0.0
                                                = +0.0
                                < Double.MIN_VALUE < Double.MIN_NORMAL < ...
```

The notation `-0.0 = +0.0` here refers to ordinary numeric comparison (`==`), not claiming the two bit representations are identical. Under `Double.compare` or `Double.equals`, different rules govern how the two signed zeros are distinguished.

## 8. Underflow: From Normal Through Subnormal Back to 0

*Underflow* occurs when a computed result falls very close to 0 relative to the range/precision of the floating-point type. It can produce a **subnormal** number, or **signed 0** if the result is too small to round to a nonzero value.

```java
double justSubnormal = Double.MIN_NORMAL / 2.0;
double underflowToZero = Double.MIN_VALUE / 2.0;

System.out.println(justSubnormal > 0.0);  // true
System.out.println(justSubnormal < Double.MIN_NORMAL); // true
System.out.println(underflowToZero);       // 0.0
```

Because `MIN_VALUE` is already the smallest nonzero subnormal step, dividing by 2 yields a mathematical value halfway between 0 and `MIN_VALUE`; under the default round-to-nearest, ties-to-even mode, the result is `+0.0`.

Similarly, `-Double.MIN_VALUE / 2.0` rounds to `-0.0`; **the sign can be preserved even when magnitude drops to 0**.

The subnormal region is useful because subtracting very small numbers can still produce a nonzero result instead of dropping abruptly to 0. However, subnormal numbers have fewer significant bits, so their **relative accuracy is lower** than that of normal numbers.

**Do not use** `Double.MIN_VALUE` as a “standard small epsilon tolerance” for general approximate comparisons. It is far too small compared to arithmetic errors at typical magnitudes such as near 1 or 1000.

## 9. ULP and nextUp/nextDown: How to Inspect Adjacent Values

*ULP* (*unit in the last place*) describes the spacing between representable values in a given magnitude region. In Java:

- `Math.ulp(x)` gives the unit step near x according to the API's definition.
- `Math.nextUp(x)` returns the representable floating-point number immediately above x.
- `Math.nextDown(x)` returns the representable number immediately below x.

Boundary verification examples:

```java
System.out.println(Math.nextUp(0.0) == Double.MIN_VALUE); // true
System.out.println(Math.nextDown(Double.MIN_NORMAL)
        + Double.MIN_VALUE == Double.MIN_NORMAL);         // true
System.out.println(Math.nextUp(Double.MAX_VALUE));       // Infinity
System.out.println(Math.ulp(0.0) == Double.MIN_VALUE);    // true
```

For normal numbers, the spacing between adjacent numbers **is not constant across the number line**: as magnitude increases, the step between representable values typically scales by powers of 2.

Example:

```java
System.out.println(Math.ulp(1.0));    // 2.220446049250313E-16
System.out.println(Math.ulp(2.0));    // 4.440892098500626E-16
```

Consequently, a condition such as `Math.abs(a - b) < Double.MIN_VALUE` practically accepts only an exact difference of 0 in many number regions; for approximate comparison, choose **absolute/relative error tolerances based on the business domain** (and account for infinity, NaN, and near-zero values).

## 10. Special Numbers: NaN, Infinity, Positive/Negative Zero

Beyond ordinary normal and subnormal finite numbers, IEEE 754 includes:

| Value | Creation Example | Characteristics |
| --- | --- | --- |
| `Double.POSITIVE_INFINITY` | `1.0 / 0.0` | Non-finite, greater than every finite number |
| `Double.NEGATIVE_INFINITY` | `-1.0 / 0.0` | Non-finite, less than every finite number |
| `Double.NaN` | `0.0 / 0.0` | “Not a Number”, special arithmetic comparison rules |
| `+0.0` | `0.0` | Positive-signed zero |
| `-0.0` | `-0.0` | Negative-signed zero; `1.0 / -0.0` yields `-Infinity` |

```java
double x = Double.NaN;
System.out.println(x == x);             // false
System.out.println(Double.isNaN(x));     // true
System.out.println(Double.isFinite(x));  // false
```

Do not test for NaN using `x == Double.NaN`. Use `Double.isNaN(x)`. For infinity use `Double.isInfinite(x)`, and `Double.isFinite(x)` identifies finite numbers (including normal, subnormal, and both ±0.0).

If an API requires a “positive and finite number,” the condition can be:

```java
static boolean positiveFinite(double x) {
    return Double.isFinite(x) && x > 0.0;
}
```

This condition accepts positive subnormals. If the domain wants to accept only **positive normals**, it must explicitly state and check `x >= Double.MIN_NORMAL` (while keeping `isFinite`). The condition `x >= Double.MIN_VALUE` does **not** substitute for a normal check.

## 11. Inspecting Bits: How the Three Constants Differ in Exponent/Fraction

Examining the bit structure connects decimal values to IEEE 754 representation:

| Constant | Hex of Full Raw Bits | Meaning |
| --- | --- | --- |
| `Float.MIN_VALUE` | `0x00000001` | exponent=0, fraction has lowest bit set |
| `Float.MIN_NORMAL` | `0x00800000` | stored exponent equals 1, fraction=0 |
| `Float.MAX_VALUE` | `0x7f7fffff` | largest finite exponent, fraction all 1s |
| `Double.MIN_VALUE` | `0x0000000000000001` | exponent=0, fraction has lowest bit set |
| `Double.MIN_NORMAL` | `0x0010000000000000` | stored exponent equals 1, fraction=0 |
| `Double.MAX_VALUE` | `0x7fefffffffffffff` | largest finite exponent, fraction all 1s |

In Java:

```java
int fBits = Float.floatToRawIntBits(Float.MIN_NORMAL);
long dBits = Double.doubleToRawLongBits(Double.MIN_NORMAL);
System.out.printf("float bits = %08x%n", fBits);  // 00800000
System.out.printf("double bits = %016x%n", dBits); // 0010000000000000
```

Note: **raw bits** are the full encoding of sign, exponent, and fraction bits, whereas `Double.toHexString` represents the **mathematical value** using a hex significand and binary exponent. The two forms serve different purposes; do not confuse them as the same string.

`Double.toHexString(Double.MIN_VALUE)` produces `"0x0.0000000000001p-1022"`; this is the exact same value as the shorter literal `0x1p-1074`. The leading `0` before the point indicates a subnormal when the API formats relative to the lowest normal exponent.

## 12. Standalone Compiling and Runnable Java 17+ Example

Create the file **`FloatingPointLimitsDemo.java`**:

```java
public class FloatingPointLimitsDemo {
    public static void main(String[] args) {
        System.out.println("Float.MIN_VALUE = " + Float.MIN_VALUE);
        System.out.println("Float.MIN_NORMAL = " + Float.MIN_NORMAL);
        System.out.println("Float.MAX_VALUE = " + Float.MAX_VALUE);

        System.out.println("Double.MIN_VALUE = " + Double.MIN_VALUE);
        System.out.println("Double.MIN_NORMAL = " + Double.MIN_NORMAL);
        System.out.println("Double.MAX_VALUE = " + Double.MAX_VALUE);

        System.out.println("Double.MIN_VALUE > 0 = "
                + (Double.MIN_VALUE > 0.0));
        System.out.println("Double.MIN_VALUE < Double.MIN_NORMAL = "
                + (Double.MIN_VALUE < Double.MIN_NORMAL));
        System.out.println("-MAX finite = "
                + Double.isFinite(-Double.MAX_VALUE));

        double subnormal = Double.MIN_NORMAL / 2.0;
        double zero = Double.MIN_VALUE / 2.0;
        double infinity = Double.MAX_VALUE * 2.0;

        System.out.println("normal / 2 is subnormal = "
                + (subnormal > 0.0 && subnormal < Double.MIN_NORMAL));
        System.out.println("MIN_VALUE / 2 = " + zero);
        System.out.println("MAX_VALUE * 2 = " + infinity);
        System.out.println("nextUp(0) = " + Math.nextUp(0.0));
        System.out.println("nextUp(MAX_VALUE) = "
                + Math.nextUp(Double.MAX_VALUE));

        System.out.println("float raw MIN_NORMAL = "
                + String.format("%08x",
                        Float.floatToRawIntBits(Float.MIN_NORMAL)));
        System.out.println("double raw MIN_VALUE = "
                + String.format("%016x",
                        Double.doubleToRawLongBits(Double.MIN_VALUE)));
        System.out.println("double MIN_VALUE hex = "
                + Double.toHexString(Double.MIN_VALUE));

        System.out.println("+0 == -0 = " + (0.0 == -0.0));
        System.out.println("1 / -0 = " + (1.0 / -0.0));
    }
}
```

Compile and run:

```bash
javac FloatingPointLimitsDemo.java
java FloatingPointLimitsDemo
```

**Expected stdout in Java 17+:**

```text
Float.MIN_VALUE = 1.4E-45
Float.MIN_NORMAL = 1.17549435E-38
Float.MAX_VALUE = 3.4028235E38
Double.MIN_VALUE = 4.9E-324
Double.MIN_NORMAL = 2.2250738585072014E-308
Double.MAX_VALUE = 1.7976931348623157E308
Double.MIN_VALUE > 0 = true
Double.MIN_VALUE < Double.MIN_NORMAL = true
-MAX finite = true
normal / 2 is subnormal = true
MIN_VALUE / 2 = 0.0
MAX_VALUE * 2 = Infinity
nextUp(0) = 4.9E-324
nextUp(MAX_VALUE) = Infinity
float raw MIN_NORMAL = 00800000
double raw MIN_VALUE = 0000000000000001
double MIN_VALUE hex = 0x0.0000000000001p-1022
+0 == -0 = true
1 / -0 = -Infinity
```

Key observations:

1. Both `Float.MIN_VALUE` and `Double.MIN_VALUE` are positive, very small, and **smaller than `MIN_NORMAL`**.
2. Dividing `MIN_NORMAL` by 2 still yields a positive finite number in the subnormal range.
3. Dividing `MIN_VALUE` by 2 produces 0 due to underflow/rounding.
4. Multiplying `MAX_VALUE` by 2 produces infinity due to overflow.
5. The raw-bit hex outputs confirm the exponent/fraction differences; `toHexString` gives the floating-point value representation.

## 13. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| “`Double.MIN_VALUE` is the smallest negative number” | It is the **smallest nonzero positive** number; the finite negative number with largest magnitude is `-Double.MAX_VALUE` |
| “`MIN_NORMAL` and `MIN_VALUE` are the same” | `MIN_VALUE` is the smallest subnormal; `MIN_NORMAL` is the smallest normal |
| “Anything smaller than `MIN_NORMAL` is 0” | Many nonzero subnormal numbers exist below it |
| “Any value smaller than `MIN_VALUE` is rejected at runtime” | Operations can underflow and round to 0; no exception is thrown by default |
| “`MAX_VALUE` is Infinity” | `MAX_VALUE` is still finite; operations exceeding the bound can become Infinity |
| “`MIN_VALUE` is an epsilon for approximate comparisons” | It is merely the smallest subnormal magnitude, far too small for most real comparisons |
| “The `==` operator distinguishes `+0.0` and `-0.0`” | `+0.0 == -0.0` is true, even though raw bits and division by zero differ |
| “`Double.toHexString` returns raw bits” | It returns the hex significand and binary exponent of the **value**, unlike bit fields |
| “Subnormals maintain the same relative precision as normals” | Effective significant bits decrease as values approach 0 |
| “Use `Double.MIN_VALUE` to reject NaN” | NaN requires `Double.isNaN`; use `Double.isFinite` when finite numbers are needed |
| “`Float.MIN_VALUE` is always smaller than `Double.MIN_VALUE` because float has fewer bits” | The opposite in **magnitude**: `Float.MIN_VALUE` is vastly larger than `Double.MIN_VALUE` |

## 14. Exercises with Solutions

**Exercise 1.** Which constant is less than 0: `Double.MIN_VALUE` or `-Double.MAX_VALUE`?  
**Solution:** Only `-Double.MAX_VALUE` is less than 0. `Double.MIN_VALUE > 0`.

**Exercise 2.** Does `Double.MIN_NORMAL / 2.0` equal 0?  
**Solution:** No; it is a representable positive **subnormal** number, smaller than `MIN_NORMAL`.

**Exercise 3.** Write the power-of-2 form for `Float.MIN_VALUE` and `Float.MIN_NORMAL`.  
**Solution:** `2^-149` and `2^-126`, respectively. They are separated by many orders of magnitude despite both being small.

**Exercise 4.** What is the value of `Math.nextUp(0.0)`?  
**Solution:** `Double.MIN_VALUE`, the representable positive number immediately after 0.

**Exercise 5.** What does `Double.MAX_VALUE * 2.0` print?  
**Solution:** `Infinity` due to overflow, not an exception.

**Exercise 6.** What does `Double.MIN_VALUE / 2.0` produce?  
**Solution:** `+0.0` because the result is too small to represent under default round-to-nearest; right at half of the smallest step, *ties to even* selects 0.

**Exercise 7.** Is `double x = 1e-320;` normal or subnormal?  
**Solution:** It is a **positive subnormal**: still larger than `Double.MIN_VALUE` yet smaller than `Double.MIN_NORMAL ≈ 2.225e-308`.

**Exercise 8.** Between `Float.MIN_VALUE` and `Double.MIN_VALUE`, which constant represents a smaller magnitude?  
**Solution:** `Double.MIN_VALUE` is smaller because `2^-1074 < 2^-149`. Yet both are the smallest nonzero positive values **in their respective types**.

## 15. Checklist When Handling Floating-Point Boundaries

1. **Choose the right concept:** do you need the smallest nonzero positive number (`MIN_VALUE`), the smallest normal number (`MIN_NORMAL`), or the largest finite number (`MAX_VALUE`)?
2. **Do not confuse with integers:** `Integer.MIN_VALUE` is negative, whereas `Double.MIN_VALUE` is positive.
3. **Check finite domain:** use `Double.isFinite(x)` or `Float.isFinite(x)` if NaN/infinity must not be accepted.
4. **Watch for underflow:** operations can become subnormal and then ±0 without throwing an error automatically.
5. **Watch for overflow:** operations can return ±Infinity; check results if that breaks domain invariants.
6. **Determine precision needs:** subnormals have fewer relative significant bits; `Math.ulp`/`Math.nextUp` are useful for understanding representation steps.
7. **Design comparisons carefully:** do not use `MIN_VALUE` as a general epsilon; choose tolerances from the nature of the data.
8. **If exact decimal is needed:** `BigDecimal` from strings and scale/rounding rules is a separate problem from the IEEE 754 domain of `float`/`double`.

**Remember:** In Java floating-point, `MIN_VALUE` is the **smallest positive subnormal**, `MIN_NORMAL` is the **smallest positive normal**, and `MAX_VALUE` is the **largest positive finite number**. These three constants describe three distinct boundaries of IEEE 754 representation; understanding them accurately helps you control underflow, overflow, and precision near 0.