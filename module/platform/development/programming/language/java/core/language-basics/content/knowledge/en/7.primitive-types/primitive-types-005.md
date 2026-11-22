# `float` and `double` in the Binary Floating-Point Model — Java 17+

## 1. Why Are Real Numbers in Computers Not Always Exact?

In Java, `float` and `double` are **binary floating-point primitive types**, conforming to the IEEE 754 model. They store a **binary value with a finite number of bits**, not every decimal number in the exact form humans write.

For example:

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum);
System.out.println(sum == 0.3);
~~~

Output:

~~~text
0.30000000000000004
false
~~~

The reason is not that Java adds incorrectly. Decimal values such as `0.1` and `0.2` have no exact finite binary representation, so they are rounded to the nearest value storable in `double`. After addition and rounding, the result differs from the nearest `double` value representing the literal `0.3`.

**Key message:** `float` and `double` represent **approximate real numbers with finite precision**; you should not assume every `==` equality comparison reflects mathematical equality on decimal numbers.

## 2. Bit Structure: Sign, Exponent, and Significand

In terms of representation, both types consist of a **sign bit**, an **exponent** field, and a **fraction/significand** field.

| Characteristic | `float` | `double` |
|---|---:|---:|
| Total bits | 32 | 64 |
| Sign bit | 1 | 1 |
| Exponent field bits | 8 | 11 |
| Stored fraction bits | 23 | 52 |
| Effective significand precision for normal numbers | 24 bits | 53 bits |
| Commonly used estimate of significant decimal digits | about 6–7 | about 15–16 |
| Largest finite positive value | about `3.4028235E38` | about `1.7976931348623157E308` |

For a non-zero **normal** number, the value takes the general form:

\[
(-1)^{sign}\times(1.fraction)_2\times2^{exponent-bias}.
\]

- `sign` indicates positive/negative sign.
- `fraction` is the fractional bits after the binary point.
- `exponent` determines the magnitude scale based on powers of 2.
- For normal numbers, there is an implicit leading `1` bit, so the effective precision is 24 or 53 bits.

**Subnormal** numbers, zero, infinities, and NaN use special representation forms and do not apply the normal-number formula verbatim.

Since Java 17, floating-point semantics are defined as **always-strict**: developers can rely on the language's rounding and width rules rather than assuming the JVM arbitrarily keeps intermediate results in extended precision. You do not need to add `strictfp` just to enable that in Java 17.

## 3. Literals, the `F` Suffix, and the Default Type

A literal with a decimal point or exponent such as `1.25` typically has type **`double`** if it has no suffix. To make a `float` literal, write the `f` or `F` suffix.

~~~java
double distanceKm = 12.5;     // double literal
double large = 1.23e6;       // 1_230_000.0, type double
float temperature = 26.5f;   // float literal
float ratio = 1.25F;         // float literal
double fromFloat = 1.25f;    // float literal widened to double
~~~

Invalid:

~~~java
// float bad = 0.1; // Compile error: double does not automatically narrow to float
~~~

If you want `float`, write `0.1f` instead of casting arbitrarily. Unless the problem has a specific reason to choose `float`, **`double` is usually the default choice** for floating-point calculations in Java.

**Do not confuse suffixes:** `L` is for `long` integer literals; `F` is for `float` floating-point literals; `D` can be written for `double` but is usually unnecessary.

The 64-bit width of `double` does not mean it represents **every** 64-bit integer accurately: once numbers are large enough, consecutive integers can round to the same `double`.

## 4. Representation Error Begins When Storing the Value

In decimal, `1/10 = 0.1` has one digit after the decimal point. In binary, `1/10` repeats infinitely, so `float`/`double` must round it within the bit limit.

~~~java
float f = 0.1f;
double d = 0.1;

System.out.println(f);
System.out.println((double) f);
System.out.println(d);
~~~

Output:

~~~text
0.1
0.10000000149011612
0.1
~~~

Explanation:

- `System.out.println(f)` displays a **short decimal string sufficient to reconstruct** the same `float` value under string-conversion rules. Printing `0.1` does not prove the stored binary value equals exact 1/10.
- Casting `float` to `double` preserves the exact **approximate value already stored in `float`**, because every finite `float` value is representable exactly in `double`. It does not restore the original decimal `0.1`.
- `double d = 0.1;` chooses a different approximation, usually more accurate due to having 53 significand bits.

If deeper analysis is needed, you can use `Float.floatToRawIntBits` and `Double.doubleToRawLongBits` to inspect the bit patterns; in application development, you only need to understand that `float`/`double` are not exact decimal types.

## 5. Value Range, `MIN_VALUE`, and Subnormal Numbers

Both types have huge value ranges, yet **finite precision**. Java provides the constants:

| Constant | Meaning | Approximate value |
|---|---|---:|
| `Float.MAX_VALUE` | Largest finite positive `float` | `3.4028235E38` |
| `Float.MIN_NORMAL` | Smallest positive normal `float` | `1.17549435E-38` |
| `Float.MIN_VALUE` | Smallest positive non-zero subnormal `float` | `1.4E-45` |
| `Double.MAX_VALUE` | Largest finite positive `double` | `1.7976931348623157E308` |
| `Double.MIN_NORMAL` | Smallest positive normal `double` | `2.2250738585072014E-308` |
| `Double.MIN_VALUE` | Smallest positive non-zero subnormal `double` | `4.9E-324` |

**Important trap:** `Float.MIN_VALUE` and `Double.MIN_VALUE` **are not the smallest negative numbers**. They are the **smallest positive non-zero numbers** representable. The finite negative numbers with the largest magnitude are `-Float.MAX_VALUE` and `-Double.MAX_VALUE`, respectively.

**Subnormals** allow representing values closer to 0 than `MIN_NORMAL` by gradually sacrificing effective significant bits. If a calculation yields a value with too small a magnitude, the result may **underflow** to a subnormal value or to (signed) zero. If the magnitude exceeds the finite range, the result can become **Infinity**.

Do not confuse "wide range" with "high precision at every value." The spacing between two consecutive floating-point numbers **increases as the magnitude of the number increases**.

## 6. Precision, ULP, and the Step Between Two Numbers

**ULP** (*unit in the last place*) helps describe the spacing between representable values near a specific number. Near `1.0`:

~~~java
System.out.println(Math.ulp(1.0f)); // 1.1920929E-7
System.out.println(Math.ulp(1.0d)); // 2.220446049250313E-16
~~~

For `float`, the integer `16_777_216` (2²⁴) is already large enough that it **cannot be distinguished** from adding 1 after rounding to `float`:

~~~java
float base = 16_777_216f;
System.out.println(base + 1f == base); // true
~~~

In `double`, consecutive integers are represented accurately up to `2^53`, after which every increment by 1 is no longer guaranteed to be distinguishable.

Thus, the ability to store **very large values** does not mean **very small differences** are preserved on the same value scale. Choosing between `double` and `float` must consider both magnitude and required resolution.

## 7. Comparisons: `==`, Epsilon, and the Limits of Tolerance

Direct comparison:

~~~java
double a = 0.1 + 0.2;
double b = 0.3;

System.out.println(a == b); // false
~~~

If a problem allows approximate error, you can define a **meaningful tolerance**:

~~~java
static boolean nearlyEqual(double a, double b, double tolerance) {
    if (tolerance < 0 || !Double.isFinite(tolerance)) {
        throw new IllegalArgumentException("Invalid tolerance");
    }
    return Double.isFinite(a) && Double.isFinite(b)
            && Math.abs(a - b) <= tolerance;
}
~~~

For example, `nearlyEqual(0.1 + 0.2, 0.3, 1e-9)` returns `true`.

However, **there is no single fixed epsilon right for every problem**: an absolute tolerance of `1e-9` might be too large when measuring nano-units and too small when comparing very large values. When needed, consider combining absolute and relative tolerances based on the data domain.

In particular, **do not use approximate comparisons** in place of identifiers, keys, monetary data, or checks that require exact equality under business rules. For `NaN` and `Infinity`, define a separate policy on whether those values are accepted.

## 8. Special Values: `NaN`, `Infinity`, `+0.0`, and `-0.0`

IEEE 754 allows several states beyond ordinary finite numbers:

| Value | How it is produced (example) | What to remember |
|---|---|---|
| `Double.POSITIVE_INFINITY` | `1.0 / 0.0` | Positive infinity, not a finite number |
| `Double.NEGATIVE_INFINITY` | `-1.0 / 0.0` | Negative infinity |
| `Double.NaN` | `0.0 / 0.0` | Not a Number |
| `+0.0` | `0.0` | Positive zero |
| `-0.0` | `-0.0` | Negative zero, has a different bit pattern from +0.0 |

Example:

~~~java
double nan = 0.0 / 0.0;
System.out.println(Double.isNaN(nan)); // true
System.out.println(nan == nan);        // false
System.out.println(1.0 / 0.0);         // Infinity
System.out.println(1.0 / -0.0);        // -Infinity
System.out.println(0.0 == -0.0);       // true
~~~

**Important distinctions:**

- Every numeric `==` comparison with NaN returns `false`, including `nan == nan`. Use `Double.isNaN` or `Float.isNaN` when you need to detect NaN.
- `0.0 == -0.0` is `true` under the `==` operator, but the sign can affect reciprocal division results and the stored bit pattern.
- Use `Double.isInfinite` or `Double.isFinite` to check for cases outside the finite range.
- Unlike integer division by 0, floating-point division `1.0 / 0.0` **does not throw `ArithmeticException`**; it produces Infinity according to floating-point rules.

If input data must not contain NaN/Infinity, validate it **before** computing or storing data in the system.

## 9. Complete Java 17 Program and Run Results

Create the exact file **`BinaryFloatingDemo.java`**:

~~~java
import java.math.BigDecimal;

public final class BinaryFloatingDemo {
    private BinaryFloatingDemo() {}

    static boolean nearlyEqual(double a, double b, double tolerance) {
        if (tolerance < 0 || !Double.isFinite(tolerance)) {
            throw new IllegalArgumentException("Invalid tolerance");
        }
        return Double.isFinite(a) && Double.isFinite(b)
                && Math.abs(a - b) <= tolerance;
    }

    public static void main(String[] args) {
        float f = 0.1f;
        double d = 0.1;

        System.out.println("float bits=" + Float.SIZE);
        System.out.println("double bits=" + Double.SIZE);
        System.out.println("float printed=" + f);
        System.out.println("float as double=" + (double) f);
        System.out.println("double printed=" + d);

        double sum = 0.1 + 0.2;
        System.out.println("0.1+0.2=" + sum);
        System.out.println("equals 0.3=" + (sum == 0.3));
        System.out.println("near 0.3=" + nearlyEqual(sum, 0.3, 1e-9));

        System.out.println("float ULP at 1=" + Math.ulp(1.0f));
        System.out.println("double ULP at 1=" + Math.ulp(1.0d));
        float base = 16_777_216f;
        System.out.println("float loses +1=" + (base + 1f == base));

        System.out.println("float min normal=" + Float.MIN_NORMAL);
        System.out.println("float min positive=" + Float.MIN_VALUE);
        System.out.println("double max finite=" + Double.MAX_VALUE);

        double nan = 0.0 / 0.0;
        System.out.println("positive infinity=" + (1.0 / 0.0));
        System.out.println("negative infinity=" + (1.0 / -0.0));
        System.out.println("is NaN=" + Double.isNaN(nan));
        System.out.println("NaN equals itself=" + (nan == nan));
        System.out.println("zero equality=" + (0.0 == -0.0));

        BigDecimal exact = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("decimal exact sum=" + exact);
    }
}
~~~

Requirement: **JDK 17+**, terminal opened in the directory containing the file.

**Bash (Linux/macOS):**

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 BinaryFloatingDemo.java
java -cp . BinaryFloatingDemo
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
javac --release 17 -encoding UTF-8 .\BinaryFloatingDemo.java
java -cp . BinaryFloatingDemo
~~~

**Expected output:**

~~~text
float bits=32
double bits=64
float printed=0.1
float as double=0.10000000149011612
double printed=0.1
0.1+0.2=0.30000000000000004
equals 0.3=false
near 0.3=true
float ULP at 1=1.1920929E-7
double ULP at 1=2.220446049250313E-16
float loses +1=true
float min normal=1.17549435E-38
float min positive=1.4E-45
double max finite=1.7976931348623157E308
positive infinity=Infinity
negative infinity=-Infinity
is NaN=true
NaN equals itself=false
zero equality=true
decimal exact sum=0.3
~~~

In the output, the `E` indicates the base-10 exponent of the **display string**; it does not change the underlying binary data nature. The display string and the bit pattern in the JVM are two different aspects of the same value.

## 10. When to Use `float`, `double`, and `BigDecimal`?

| Need | Typical choice | Reason |
|---|---|---|
| General scientific/statistical calculations with tolerance | `double` | About 15–16 significant decimal digits; higher accuracy than `float` |
| Very large arrays, image/graphics data, interfaces requiring 32 bits | `float` when suitable | Lower data footprint, but larger error |
| Currency/strict decimal rounding rules | `BigDecimal` or integer smallest units | Requires business-rule arithmetic and rounding, not binary approximation |
| Integer counts | `int` or `long` | Integer counts do not need floating-point |

**`BigDecimal` is not a suffix of `float`/`double`.** It is an object type in `java.math`, with its own rules and arithmetic API.

When you need to represent **exact decimal numbers in monetary problems**, create `BigDecimal` from a **decimal string** or from a known representation, for example:

~~~java
BigDecimal price = new BigDecimal("0.1");
BigDecimal tax = new BigDecimal("0.2");
System.out.println(price.add(tax)); // 0.3
~~~

Avoid `new BigDecimal(0.1)` if the goal is to get the **exact decimal value 0.1**: this constructor receives the binary-approximated `double` value and preserves that discrepancy. `BigDecimal.valueOf(0.1)` is also a reasonable option in many cases to convert a `double` via its canonical string representation, but it **cannot recover precision already lost in prior calculations**.

For non-terminating decimal division, `BigDecimal` may require an appropriate rounding rule/`MathContext`. Choosing `BigDecimal` does not remove the need to define a rounding policy.

## 11. Common Mistakes and How to Check

| Symptom | Cause | How to handle |
|---|---|---|
| `float f = 0.1;` fails to compile | Default literal is `double` | `float f = 0.1f;` |
| `0.1 + 0.2 == 0.3` is false | Binary rounding | Use an appropriate tolerance or an exact decimal model |
| `Float.MIN_VALUE` is mistaken for the most negative number | Misleading constant name | Remember this is the smallest non-zero positive number |
| `float` loses an increment of 1 at large numbers | Spacing between float values is already large | Choose `double` or an integer type if counting |
| `1.0 / 0.0` gives Infinity | IEEE 754 semantics | Use `isFinite`/validation |
| `NaN == NaN` is false | NaN has special comparison rules | Use `isNaN` |
| `0.0 == -0.0` is true | Value comparison does not distinguish zero sign | Check bits/sign if the problem needs to distinguish them |
| `new BigDecimal(0.1)` has long trailing digits | Receives binary double near 0.1 | Use a decimal string or `valueOf` appropriately |
| Using a fixed absolute epsilon for all number scales | Tolerance does not fit the data domain | Define absolute/relative error per requirements |
| Expecting `double` to preserve all 64-bit integers | Significand is only 53 bits | Use `long`/`BigInteger` when exact integers are needed |

## 12. Short Exercises with Answers

### Exercise A — Literal Types

~~~java
double a = 1.25;
float b = 1.25f;
// float c = 1.25;
~~~

**Answer:** `a` and `b` are valid. Line `c` fails to compile because `1.25` is a `double` literal without the `f` suffix. Even though this value can be represented exactly in binary, the literal type rule still applies.

### Exercise B — Printed Value Differs from True Value

~~~java
float value = 0.1f;
System.out.println(value);
System.out.println((double) value);
~~~

**Answer:**

~~~text
0.1
0.10000000149011612
~~~

`println(float)` and `println(double)` use per-type value-to-string conversion. Casting `float` to `double` does not turn the value into exact decimal 0.1.

### Exercise C — Comparing Floating-Point Numbers

Why does `0.1 + 0.2 == 0.3` return false? What should be done if the problem allows an error of 1e-9?

**Answer:** the values are rounded in binary, so after addition the result may not match the exact bit pattern of `0.3`. You can compare `Math.abs((0.1 + 0.2) - 0.3) <= 1e-9` if this tolerance fits the data domain, while also having separate rules for NaN/Infinity.

### Exercise D — Special Numbers

~~~java
double x = 0.0 / 0.0;
System.out.println(Double.isNaN(x));
System.out.println(x == x);
~~~

**Answer:**

~~~text
true
false
~~~

### Exercise E — Currency

You need to add two monetary values in decimal, 0.1 and 0.2, to get exactly 0.3. What should you choose?

**Answer:** `new BigDecimal("0.1").add(new BigDecimal("0.2"))` yields `0.3` accurately in decimal representation; for finite smallest units, integers can be considered. Avoid treating `double` addition as exact decimal arithmetic.

## 13. Completion Checklist

- [ ] Know that `float` has 32 bits and `double` has 64 bits; effective significands are 24/53 bits respectively.
- [ ] Understand why `0.1` cannot be represented exactly with a finite number of binary bits.
- [ ] Remember that floating-point literals default to `double`; use `f`/`F` for `float`.
- [ ] Distinguish the printed string `0.1` from the stored binary value.
- [ ] Understand that `MIN_VALUE` is the smallest non-zero positive number, distinct from `MIN_NORMAL`.
- [ ] Know that resolution decreases as magnitude increases, observable via `Math.ulp`.
- [ ] Know how to detect NaN/Infinity using dedicated APIs and distinguish `+0.0`/`-0.0`.
- [ ] Do not apply a universal epsilon to every problem without considering scale.
- [ ] Know when to switch to `BigDecimal` or integers.
- [ ] Compile/run `BinaryFloatingDemo.java` with `javac`/`java` and verify each line.

**Conclusion:** `float` and `double` represent real numbers using **binary floating-point**, offering a very wide range while retaining only a finite number of significant bits. Anticipate rounding errors, choose types according to precision requirements, check special values, and use an appropriate decimal model when business logic demands exact decimal results.
