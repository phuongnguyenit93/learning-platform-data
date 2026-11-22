# `float` as binary32 and `double` as binary64 in Java

`float` and `double` are both primitive types for working with binary floating-point numbers in Java. `float` uses **IEEE 754 binary32 (32-bit)**, while `double` uses **IEEE 754 binary64 (64-bit)**. The first distinction to grasp is **resolution and representable magnitude range**, not a fixed number of digits after the decimal point.

This lesson focuses on **comparing the two formats and deciding which type to choose**. Subsequent lessons cover bit decoding, precision analysis, underflow, special values, and bit-conversion APIs in dedicated depth.

## 1. Comparison Table of binary32 and binary64

| Property | `float` (binary32) | `double` (binary64) |
| --- | --- | --- |
| Total width | 32 bits | 64 bits |
| Sign bit | 1 | 1 |
| Stored exponent field | 8 bits | 11 bits |
| Stored fraction field | 23 bits | 52 bits |
| Significand of a normal number, including implicit leading 1 bit | 24 bits | 53 bits |
| Exponent bias | 127 | 1023 |
| Actual exponent in the normal range | −126 to +127 | −1022 to +1023 |
| Significant decimal digits commonly used as an estimate | About 6–7 | About 15–16 |
| Smallest positive normal number | `Float.MIN_NORMAL = 2^-126` | `Double.MIN_NORMAL = 2^-1022` |
| Smallest nonzero positive number | `Float.MIN_VALUE = 2^-149` | `Double.MIN_VALUE = 2^-1074` |
| Largest finite positive number | `Float.MAX_VALUE ≈ 3.4 × 10^38` | `Double.MAX_VALUE ≈ 1.8 × 10^308` |

In a **normal** number, a leading 1 bit in the significand is implicit. Therefore, the 23/52-bit fraction field provides **24/53 bits of precision**, respectively. For **subnormal** numbers very close to zero, this leading bit is absent; relative accuracy decreases gradually. `MIN_VALUE` on both floating-point wrapper classes is the **smallest nonzero positive number**, not the smallest finite negative number; the finite negative number with the largest magnitude is `-MAX_VALUE`.

### Large Range Does Not Mean Unit-Exact Precision

The **exponent** allows a wide variation in magnitude. The **significand** limits the detail between numbers at the same magnitude. For example, binary32 can hold finite numbers around `10^38`, yet around `2^24` it can no longer distinguish all adjacent integers. Similarly, binary64 does not consecutively distinguish every integer past `2^53`.

Thanks to having more exponent and fraction bits, binary64 can represent numbers across a wider magnitude range and is usually closer to the mathematical value than binary32. However, neither type can store **every decimal fraction** exactly.

## 2. Observing the Same Input Value in Both Formats

In Java, the literal `0.1` is `double` by default; the `f` suffix creates a `float` literal:

```java
float lowPrecision = 0.1f;
double highPrecision = 0.1;
double widened = lowPrecision;

System.out.println(lowPrecision);            // 0.1
System.out.println(highPrecision);           // 0.1
System.out.println(widened);                 // 0.10000000149011612
System.out.println(Float.toHexString(lowPrecision));
// 0x1.99999ap-4
System.out.println(Double.toHexString(highPrecision));
// 0x1.999999999999ap-4
```

`1/10` has an infinite binary expansion, so each format stores the closest number within its precision. The first two `println` calls both print `0.1` because Java chooses a string that can round-trip back to the **value stored in each respective type**. When `float` is widened to `double`, Java preserves the exact **rounded binary32 value**; widening does not reconstruct the original 1/10 fraction.

To inspect the encoding instead of a decimal string, use the bit APIs:

```java
System.out.printf("0x%08x%n", Float.floatToRawIntBits(0.1f));
// 0x3dcccccd
System.out.printf("0x%016x%n", Double.doubleToRawLongBits(0.1));
// 0x3fb999999999999a
```

These are **two IEEE 754 bit patterns**, not two integers produced by numeric casting. The lesson on sign/exponent/fraction will show how to decode each field; the last two lessons in this chapter will distinguish `raw`/canonical NaN and how to reconstruct numbers from bit patterns.

## 3. Choosing a Format Based on Data Requirements

| Scenario | Typically Appropriate Type / Representation | Deciding Condition |
| --- | --- | --- |
| Scientific or business calculations accepting binary approximation | `double` | Wider precision and sufficient range needed; still evaluate arithmetic error |
| Image buffers, graphics data, or sensors requiring 32-bit | `float` | Binary32 storage/transmission contract and errors across actual value ranges are acceptable |
| Very large primitive arrays sensitive to memory and bandwidth | `float[]` if precision suffices | 4 bytes per primitive element instead of 8 bytes; also account for structural overhead |
| Counts, IDs, offsets needing unit-level exactness | `int`, `long`, or `BigInteger` | Avoid letting floating-point rounding merge two distinct integer values |
| Money, taxes, fixed-digit decimals | `BigDecimal` from strings or integer smallest units | Define scale, rounding, and exact numeric domain from the outset |
| Binary protocols that must preserve every bit, including NaN payloads | `int`, `long`, `byte[]` at the transport layer | Lock down width, byte order, and bit-exact requirements before computing |

**`double` is a reasonable default choice for many floating-point calculations in Java**, but it is not automatically the best choice when external APIs mandate binary32 or when decimal representation must be exact. Choosing `float` for storage size is only justified after verifying errors at **large, small, near-zero values, and across many computation steps**, not because two variables happen to print identically.

### Checking Bounds When Converting Types

Converting `double` to `float` is a narrowing conversion; a value that is finite in binary64 can become Infinity in binary32:

```java
double large = 1e40;
float narrowed = (float) large;
System.out.println(narrowed);            // Infinity
System.out.println(Float.isFinite(narrowed)); // false
```

Similarly, a very small number can turn into a `float` subnormal or zero. Conversely, converting `float` to `double` preserves the exact numeric value stored in the `float`, but **does not** recover information lost in an earlier conversion.

When data must remain finite, check `Float.isFinite`/`Double.isFinite` on the **post-conversion result** and enforce domain range constraints. Floating-point operators can produce NaN or Infinity without throwing `ArithmeticException`, unlike integer division by zero.

## 4. Literals, Expressions, and Rounding Points

```java
double d = 1.25;  // literal is double by default
float f = 1.25f;  // f suffix requests float
float explicitlyNarrowed = (float) d;
// float invalid = d;  // does not automatically convert double to float
```

`float` and `double` share the same set of operations, but **each operation can round** according to the precision of the type in which it executes. If an expression mixes `float` and `double`, promotion rules promote the `float` operand to `double` before the operation, still carrying the already-rounded `float` value. In Java 17+, floating-point semantics are always strict under JEP 306; this does not turn computation into exact real-number arithmetic.

An example of choosing the wrong type to store an integer:

```java
int original = 16_777_217; // 2^24 + 1
float rounded = original;
System.out.println((int) rounded); // 16777216
System.out.println(Math.ulp(16_777_216f)); // 2.0
```

Because the binary32 significand has 24 bits of precision, this integer is rounded. `double` has a similar threshold at `2^53`, which does not mean every integer larger than the threshold is unrepresentable. The lesson on **consecutive integer ranges** will analyze the endpoints and pitfalls when comparing `long` with `double`.

### One Error Threshold Does Not Fit All Numbers

`Math.ulp(1f)` is about `1.19E-7`, while `Math.ulp(1d)` is about `2.22E-16`. At larger numbers, the representation step is usually larger. An approximate-equality threshold must derive from the data and problem domain (potentially combining absolute/relative error), while also handling NaN, Infinity, and signed zero. ULP describes the representation grid; it is **not** an error bound guarantee for arbitrary sequences of operations.

## 5. A Self-Verifiable Comparison Program

Save as `FloatingFormatsComparisonDemo.java`, and run with Java 17+:

```java
public class FloatingFormatsComparisonDemo {
    public static void main(String[] args) {
        float f = 0.1f;
        double d = 0.1;

        System.out.println("float bits="
                + Integer.toHexString(Float.floatToRawIntBits(f)));
        System.out.println("double bits="
                + Long.toHexString(Double.doubleToRawLongBits(d)));
        System.out.println("float widened=" + (double) f);
        System.out.println("float precision bits=" + 24);
        System.out.println("double precision bits=" + 53);
        System.out.println("float ulp at one=" + Math.ulp(1.0f));
        System.out.println("double ulp at one=" + Math.ulp(1.0d));
        System.out.println("integer lost=" + (int) (float) 16_777_217);
        System.out.println("narrowed large=" + (float) 1e40);
        System.out.println("narrowed tiny=" + (float) 1e-50);
    }
}
```

```bash
javac --release 17 FloatingFormatsComparisonDemo.java
java FloatingFormatsComparisonDemo
```

Output (Java 17+):

```text
float bits=3dcccccd
double bits=3fb999999999999a
float widened=0.10000000149011612
float precision bits=24
double precision bits=53
float ulp at one=1.1920929E-7
double ulp at one=2.220446049250313E-16
integer lost=16777216
narrowed large=Infinity
narrowed tiny=0.0
```

The four tests use decimal values, bit patterns, ULP, and type conversions to answer four different questions: **which code** is stored, how dense the grid spacing is, what narrowing loses, and whether a value remains finite. Do not infer everything from a single `println`.

## 6. Self-Check Questions

1. Why does `float` have 23 stored fraction bits yet 24 bits of precision for normal numbers? How does that difference affect type selection?
2. Why is `float f = 0.1f; double d = f;` not equivalent to `double d = 0.1;`?
3. When is `float` a data-contract requirement, and when does `double` improve calculation quality?
4. If a sensor transmits `float` but calculations require `double`, what information stays intact during widening and what information cannot be recovered?
5. If a `double` must be used to store money exact to the cent, is the issue numeric range, precision, or representation radix?
6. How do you verify that a narrowing step from `double` to `float` still satisfies finiteness and error requirements?

## 7. Connections to In-Depth Lessons

- **Sign bit, exponent, and fraction**: decodes specifically how the 1/8/23 and 1/11/52 bits produce a value.
- **Precision, 0.1, exact integer range**: clarifies resolution, decimal, and integer-conversion errors.
- **Normal/subnormal, three boundary constants, special values, and ULP**: examines near-zero behavior, overflow, and spacing between numbers.
- **APIs for reading bits and reconstructing values**: supports debugging, bit inspection, and protocol-compliant binary data exchange.

**Remember:** the difference between binary32 and binary64 is a verifiable trade-off among **storage size, value range, and resolution**. Choose the type based on the data contract and acceptable error; choose integer types for countable quantities requiring unit exactness and an appropriate decimal type for domains requiring exact decimal arithmetic.