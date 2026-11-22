# Reference Table of Sizes, Value Ranges, and Constants for Numeric Types in Java

## 1. Scope and How to Use the Reference Table

In Java, the size and value range of **primitive types** (*primitive type*) are specified by the language and do not change simply because the code runs on Windows/Linux, a 32-bit/64-bit JVM, or different hardware. When you need to quickly look up a limit, you should use **wrapper class constants** such as `Integer.MAX_VALUE`, `Long.MIN_VALUE`, and `Double.MAX_VALUE` instead of manually retyping long numbers.

This lesson summarizes:

- Primitive types representing numeric values: `byte`, `short`, `int`, `long`, `float`, `double`; as well as explaining `char` — a 16-bit unsigned integral type used for **UTF-16 code units**.
- Bit count, byte count, representation limits, minimum/maximum values, and standard constants from the wrapper classes.
- Differences between exact integers and approximate floating-point numbers; the constants `MIN_VALUE`, `MIN_NORMAL`, `MAX_EXPONENT`, `NaN`, and `Infinity`.
- The role of `BigInteger` and `BigDecimal` when there are no fixed min/max bounds, along with how to inspect `precision()`, `scale()`, and commonly used constants.
- A Java 17+ example that can be compiled and run to verify the table via the API itself rather than memorizing it.

**Convention:** 1 byte in the `BYTES` constants here is 8 bits. The table describes the **value representation of the type**, not the amount of RAM occupied by a wrapper object, an array, a field inside an object, or a collection. Actual memory usage also includes object headers, alignment, references, data structures, and JVM optimizations.

`boolean` is not a numeric type; Java does not specify a fixed storage size for `boolean` in the same way it does for the numeric types in the table below. Therefore, `boolean` is not included in the numeric table. `char` is not a numeric data type commonly used for currency or counting, but it is an integral type and can participate in arithmetic operations through numeric promotion; hence it is listed separately.

## 2. Integer Types and char: Sizes and Value Ranges

| Java Type | Bits | Bytes | Signed? | Value Range | Bound Constants |
|---|---:|---:|---|---|---|
| `byte` | 8 | 1 | Yes | `-128` to `127` | `Byte.MIN_VALUE`, `Byte.MAX_VALUE` |
| `short` | 16 | 2 | Yes | `-32768` to `32767` | `Short.MIN_VALUE`, `Short.MAX_VALUE` |
| `int` | 32 | 4 | Yes | `-2147483648` to `2147483647` | `Integer.MIN_VALUE`, `Integer.MAX_VALUE` |
| `long` | 64 | 8 | Yes | `-9223372036854775808` to `9223372036854775807` | `Long.MIN_VALUE`, `Long.MAX_VALUE` |
| `char` | 16 | 2 | Unsigned | `0` to `65535`, i.e., `U+0000`–`U+FFFF` by code unit value | `Character.MIN_VALUE`, `Character.MAX_VALUE` |

For `byte`, `short`, `int`, and `long`, signed numbers use **two's complement**. If a type has \(n\) bits, its range is:

\[
-2^{n-1} \le x \le 2^{n-1}-1.
\]

For example, `int` has 32 bits, so its range is \(-2^{31}\) to \(2^{31}-1\). The smallest negative number has an absolute value that is exactly 1 unit greater than the largest positive number. As a result, `Math.abs(Integer.MIN_VALUE)` remains negative because `2147483648` cannot be represented as an `int`; this requires attention when writing absolute value checks.

As for `char`, it is an unsigned integer value in the range \(0\) to \(2^{16}-1\). Java uses `char` to represent **one UTF-16 code unit** and **does not guarantee that one `char` equals a complete Unicode character**. Characters outside the BMP use two code units (*surrogate pair*), so full Unicode character processing may require `String.codePoints()`, `Character.codePointAt(...)`, and the `int` type for code points.

### Corresponding Size Constants

| Type | Bit Constant | Value | Byte Constant | Value |
|---|---|---:|---|---:|
| `byte` | `Byte.SIZE` | `8` | `Byte.BYTES` | `1` |
| `short` | `Short.SIZE` | `16` | `Short.BYTES` | `2` |
| `int` | `Integer.SIZE` | `32` | `Integer.BYTES` | `4` |
| `long` | `Long.SIZE` | `64` | `Long.BYTES` | `8` |
| `char` | `Character.SIZE` | `16` | `Character.BYTES` | `2` |

The `SIZE` and `BYTES` fields are `static final` constants on the corresponding wrapper class. For example, using `Integer.SIZE` instead of hardcoding `32` in bit-width checks clarifies intent, even though the value in Java is already fixed.

### Hexadecimal Forms for Identifying Bounds and Sign Bits

| Type | Largest Positive Bound (hex) | Smallest Negative Bound (hex, two's complement pattern) |
|---|---|---|
| `byte` | `0x7F` | `0x80` |
| `short` | `0x7FFF` | `0x8000` |
| `int` | `0x7FFFFFFF` | `0x80000000` |
| `long` | `0x7FFFFFFFFFFFFFFF` | `0x8000000000000000` |

The values in the negative hex column are the **bit patterns** of the negative bounds, not an arbitrary way of writing positive numbers with hex literals. For instance, `Integer.MIN_VALUE` has the 32-bit pattern `0x80000000`. `Character.MAX_VALUE` corresponds to `0xFFFF` and has no sign bit.

## 3. Floating-Point Numbers: float and double Do Not Have "Every Value in the Range"

Java provides two binary floating-point types following IEEE 754:

| Property | `float` | `double` |
|---|---|---|
| Size | 32 bits = 4 bytes | 64 bits = 8 bytes |
| Sign bit | 1 | 1 |
| Stored exponent bits | 8 | 11 |
| Stored fraction bits | 23 | 52 |
| Effective binary precision for normal numbers | 24 bits | 53 bits |
| Approximate decimal precision | about 6–9 significant digits for round-trip | about 15–17 significant digits for round-trip |
| Largest finite positive bound | `Float.MAX_VALUE` ≈ `3.4028235E38` | `Double.MAX_VALUE` ≈ `1.7976931348623157E308` |
| Lowest finite negative bound | `-Float.MAX_VALUE` | `-Double.MAX_VALUE` |
| Smallest nonzero positive number | `Float.MIN_VALUE` = `1.4E-45` when printed with JDK 17 (JDK 19+ may print `1.1754944E-38`) | `Double.MIN_VALUE` = `4.9E-324` when printed by default |
| Smallest **normal** positive number | `Float.MIN_NORMAL` = `1.17549435E-38` when printed by default | `Double.MIN_NORMAL` = `2.2250738585072014E-308` |
| `MIN_EXPONENT` of normal numbers | `-126` | `-1022` |
| `MAX_EXPONENT` of normal numbers | `127` | `1023` |

The strings in the table are the **short decimal representations that Java prints** for those floating-point constants, not the full exact decimal expansions of those binary numbers. For example, `Float.MIN_NORMAL` has the exact binary mathematical value \(2^{-126}\), whereas `Float.toString` in JDK 17 prints `1.17549435E-38`. Starting from JDK 19, changes in the float-to-string conversion algorithm may produce a shorter form `1.1754944E-38`; the binary value and bits of the constant remain unchanged.

**Very important:** unlike `Integer.MIN_VALUE`, `Float.MIN_VALUE` and `Double.MIN_VALUE` are **not the smallest negative numbers**. They are the **smallest positive numbers greater than 0 and nonzero**, belonging to the *subnormal* category. If you need the finite lower bound of `float`/`double` values, use `-Float.MAX_VALUE` and `-Double.MAX_VALUE`.

The values representable by `float` or `double` form a **discrete set**, not every real number in the interval from the negative bound to the positive bound. The spacing between two representable numbers changes depending on magnitude; many decimal fractions such as `0.1` are not stored exactly in binary form.

### Normal, Subnormal, and Exponent

- **Normal:** has a normalized significand, receiving 24 bits (`float`) or 53 bits (`double`) of effective precision.
- **Subnormal:** values very close to 0, smaller than `MIN_NORMAL` in absolute value; uses an encoding that allows gradual underflow toward 0 with lower relative precision.
- **`MIN_EXPONENT` and `MAX_EXPONENT`:** refer to the exponent of **finite normal numbers**, not the smallest/largest exponent in any decimal display format. Do not use them as a universal threshold for `E` strings or for subnormals.
- **Zero:** has two bit patterns `+0.0` and `-0.0`, which compare equal under the primitive `==` operator.
- **Infinity and NaN:** special IEEE 754 values that do not belong to the finite number range.

### Constants for float and double

| `float` Constant | `double` Constant | Meaning |
|---|---|---|
| `Float.SIZE` | `Double.SIZE` | Bit count: 32 and 64 |
| `Float.BYTES` | `Double.BYTES` | Byte count: 4 and 8 |
| `Float.MIN_VALUE` | `Double.MIN_VALUE` | Smallest nonzero positive subnormal number |
| `Float.MIN_NORMAL` | `Double.MIN_NORMAL` | Smallest positive normal number |
| `Float.MAX_VALUE` | `Double.MAX_VALUE` | Largest finite positive number |
| `Float.MIN_EXPONENT` | `Double.MIN_EXPONENT` | Lowest binary exponent of a normal number |
| `Float.MAX_EXPONENT` | `Double.MAX_EXPONENT` | Highest binary exponent of a normal number |
| `Float.POSITIVE_INFINITY` | `Double.POSITIVE_INFINITY` | Positive infinity |
| `Float.NEGATIVE_INFINITY` | `Double.NEGATIVE_INFINITY` | Negative infinity |
| `Float.NaN` | `Double.NaN` | Not-a-Number |

You can check special values using `Float.isNaN(...)`, `Double.isNaN(...)`, `Float.isInfinite(...)`, `Double.isInfinite(...)`, and `isFinite(...)` respectively. `NaN == NaN` is `false` under the `==` operator; do not check for NaN using direct equality comparison.

For example, `Double.POSITIVE_INFINITY` **differs from** `Double.MAX_VALUE`: the former is not finite, whereas the latter is the largest positive finite number.

### Integer Range Represented Exactly in float/double

- Every integer in the range from \(-2^{24}\) to \(2^{24}\), i.e., `-16_777_216` to `16_777_216`, is represented exactly by `float`. The number `16_777_217` is not represented exactly by `float` and may round to `16_777_216`.
- Every integer in the range from \(-2^{53}\) to \(2^{53}\), i.e., `-9_007_199_254_740_992L` to `9_007_199_254_740_992L`, is represented exactly by `double`. The number `9_007_199_254_740_993L` is not represented exactly when cast to `double`.

These thresholds do not mean that every integer above the threshold is unrepresentable: for example, a sufficiently large even number can still be represented exactly, but **consecutive integers are no longer guaranteed to all be representable**.

## 4. Java 17+ Program to Verify Constants Directly on the JVM

To avoid guessing the values of constants, you can run the following lookup program. This is a standalone program whose file name matches the `public class` name.

Save the file **`NumericTypeReference.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumericTypeReference {
    public static void main(String[] args) {
        System.out.println("byte: " + Byte.SIZE + " bits, "
                + Byte.BYTES + " bytes; "
                + Byte.MIN_VALUE + ".." + Byte.MAX_VALUE);
        System.out.println("short: " + Short.SIZE + " bits, "
                + Short.BYTES + " bytes; "
                + Short.MIN_VALUE + ".." + Short.MAX_VALUE);
        System.out.println("int: " + Integer.SIZE + " bits, "
                + Integer.BYTES + " bytes; "
                + Integer.MIN_VALUE + ".." + Integer.MAX_VALUE);
        System.out.println("long: " + Long.SIZE + " bits, "
                + Long.BYTES + " bytes; "
                + Long.MIN_VALUE + ".." + Long.MAX_VALUE);
        System.out.println("char: " + Character.SIZE + " bits, "
                + Character.BYTES + " bytes; "
                + (int) Character.MIN_VALUE + ".."
                + (int) Character.MAX_VALUE);

        System.out.println("float: " + Float.SIZE + " bits, "
                + Float.BYTES + " bytes");
        System.out.println("float MIN_VALUE: " + Float.MIN_VALUE);
        System.out.println("float MIN_NORMAL: " + Float.MIN_NORMAL);
        System.out.println("float MAX_VALUE: " + Float.MAX_VALUE);
        System.out.println("float MIN_EXPONENT / MAX_EXPONENT: "
                + Float.MIN_EXPONENT + " / " + Float.MAX_EXPONENT);

        System.out.println("double: " + Double.SIZE + " bits, "
                + Double.BYTES + " bytes");
        System.out.println("double MIN_VALUE: " + Double.MIN_VALUE);
        System.out.println("double MIN_NORMAL: " + Double.MIN_NORMAL);
        System.out.println("double MAX_VALUE: " + Double.MAX_VALUE);
        System.out.println("double MIN_EXPONENT / MAX_EXPONENT: "
                + Double.MIN_EXPONENT + " / " + Double.MAX_EXPONENT);

        System.out.println("float +infinity? "
                + Float.isInfinite(Float.POSITIVE_INFINITY));
        System.out.println("double NaN? "
                + Double.isNaN(Double.NaN));

        System.out.println("big constants: "
                + BigInteger.ZERO + ", " + BigInteger.ONE + ", "
                + BigInteger.TWO + ", " + BigInteger.TEN);
        System.out.println("decimal constants: "
                + BigDecimal.ZERO + ", " + BigDecimal.ONE + ", "
                + BigDecimal.TWO + ", " + BigDecimal.TEN);

        BigDecimal decimal = new BigDecimal("123.4500");
        System.out.println("BigDecimal precision/scale: "
                + decimal.precision() + "/" + decimal.scale());
        System.out.println("BigInteger digits for 10^40: "
                + BigInteger.TEN.pow(40).toString().length());

        System.out.println("float exact-int boundary: "
                + ((float) 16_777_217 == (float) 16_777_216));
        System.out.println("double exact-long boundary: "
                + ((double) 9_007_199_254_740_993L
                        == (double) 9_007_199_254_740_992L));
    }
}
```

Run:

```bash
javac NumericTypeReference.java
java NumericTypeReference
```

Reference output with JDK 17 (some float/double strings may differ on JDK 19+):

```text
byte: 8 bits, 1 bytes; -128..127
short: 16 bits, 2 bytes; -32768..32767
int: 32 bits, 4 bytes; -2147483648..2147483647
long: 64 bits, 8 bytes; -9223372036854775808..9223372036854775807
char: 16 bits, 2 bytes; 0..65535
float: 32 bits, 4 bytes
float MIN_VALUE: 1.4E-45
float MIN_NORMAL: 1.17549435E-38
float MAX_VALUE: 3.4028235E38
float MIN_EXPONENT / MAX_EXPONENT: -126 / 127
double: 64 bits, 8 bytes
double MIN_VALUE: 4.9E-324
double MIN_NORMAL: 2.2250738585072014E-308
double MAX_VALUE: 1.7976931348623157E308
double MIN_EXPONENT / MAX_EXPONENT: -1022 / 1023
float +infinity? true
double NaN? true
big constants: 0, 1, 2, 10
decimal constants: 0, 1, 2, 10
BigDecimal precision/scale: 7/4
BigInteger digits for 10^40: 41
float exact-int boundary: true
double exact-long boundary: true
```

**How to read the key lines:**

1. `Byte.SIZE`/`Byte.BYTES` output `8`/`1`; similarly for the other types. These are specified values and do not depend on running a 64-bit JVM.
2. The `char` line casts both constants to `int` to print the **numeric codes** 0 and 65535; if you print `Character.MIN_VALUE`/`MAX_VALUE` directly, they are interpreted as characters and do not give an easily readable numeric table.
3. `Float.MIN_VALUE` and `Double.MIN_VALUE` are printed as **small positive numbers**; `MIN_NORMAL` gives the threshold from normal down to subnormal.
4. `BigInteger.TEN.pow(40)` is \(10^{40}\), which in decimal form has **41 digits**. The program uses only a small exponent for demonstration and does not encourage calling very large powers without resource limits.
5. Both `float exact-int boundary` and `double exact-long boundary` print `true`: two nearby integers with different exact values can **become equal after casting to floating point**. This result does not mean `float`/`double` have a more accurate comparison; it demonstrates **loss of the ability to distinguish two numbers**.

This is the fixed output of the constants and operations used. Java's `Float.toString`/`Double.toString` methods produce a decimal representation sufficient to read back the floating-point value according to the API contract; they do not list all decimal digits of the exact binary value.

## 5. BigInteger and BigDecimal: No Fixed Size Like Primitives

The two classes `java.math.BigInteger` and `java.math.BigDecimal` are **immutable reference classes**, not primitives. They do not have `SIZE`/`BYTES` describing a fixed storage bit count corresponding to a single numeric value, and they do not define a `MIN_VALUE`/`MAX_VALUE` pair like `Integer`.

| Property | `BigInteger` | `BigDecimal` |
|---|---|---|
| Value kind | Arbitrary-magnitude integer | Arbitrary-precision decimal number |
| Conceptual structure | Multi-bit integer data | Unscaled integer and `scale` |
| Fixed bit size? | No | No, unscaled value has arbitrary magnitude |
| Fixed min/max value bounds? | No primitive-style bound constants | No primitive-style bound constants |
| Common constants | `ZERO`, `ONE`, `TWO`, `TEN` | `ZERO`, `ONE`, `TWO`, `TEN` |
| Size properties | `bitLength()`, representation in chosen radix | `precision()`, `scale()`, `unscaledValue()` |
| Safe initialization for decimal-written numbers | `new BigInteger("12345678901234567890")` | `new BigDecimal("123.4500")` |

`BigInteger.TWO` and `BigDecimal.TWO` are available in Java 17+. Both classes also have `ZERO`, `ONE`, and `TEN` constants. Do not confuse these constants with range limits: they are **commonly used values**, not max/min bounds.

### BigInteger

`BigInteger` is not restricted to 32 or 64 bits. For example:

```java
BigInteger large = new BigInteger("9223372036854775808");
// Greater than Long.MAX_VALUE by exactly 1.

BigInteger value = BigInteger.TEN.pow(40);
System.out.println(value.toString().length()); // 41
System.out.println(value.signum());            // 1
```

`bitLength()` helps inspect bit magnitude; `signum()` returns `-1`, `0`, or `1` according to the sign. However, "arbitrary" does not mean infinite: there are still limits from memory, CPU, array length, and library implementation. In systems accepting external data, you need to limit input digit counts and operations that can produce extremely large results.

### BigDecimal

`BigDecimal` represents a value using the formula:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}.
\]

For example, `new BigDecimal("123.4500")` has an unscaled value of `1234500`, `precision() == 7`, and `scale() == 4`. Trailing zeros can affect the **scale** and representation, even though they do not affect the mathematical value.

- **Precision** is the number of decimal digits in the unscaled value (the value 0 has precision 1), not a fixed bit width.
- **Scale** is an `int` and can be negative, zero, or positive. `"1E+3"` has scale `-3`; `"1.00"` has scale `2`.
- `MathContext` can specify result precision and `RoundingMode`; `setScale(...)` specifies the scale of the result. These are **calculation/rounding rules**, not primitive value-bound constants.
- `BigDecimal` can compute exact decimals when data is constructed from strings and the operation permits it; some division operations require a precision/rounding policy.

If the input is an exact decimal number from a user or document, prefer `new BigDecimal("0.1")` instead of `new BigDecimal(0.1)`. The constructor taking `double` reflects the approximate binary value of the `0.1` supplied. `BigDecimal.valueOf(0.1)` uses the decimal representation of `Double.toString`, but does not recover data lost in earlier `double` operations.

## 6. Constants, Literals, and Conversions Related to Value Ranges

### Integer Literals: int Is Default, long Uses L

In Java, an unsuffixed decimal integer literal generally has type `int` if the value is representable; add `L` to denote a `long` literal. For example:

```java
int size = 1_000_000;
long population = 9_000_000_000L;
long max = Long.MAX_VALUE;
```

`9_000_000_000` without a suffix is not a valid `int` decimal literal even if the target variable is `long`. Assignment afterward does not turn an out-of-`int`-range literal into a valid one. Underscores may be used between digits for readability.

### Floating-Point Literals: double Is Default, float Uses F/f

`3.14` is a `double` literal; `3.14f` or `3.14F` is a `float` literal. With `float`, using the `f` suffix is required when you want to represent a floating-point literal with the `float` type:

```java
float f = 0.1f;
double d = 0.1;
```

Even when the decimal strings look identical, `f` and `d` use different numbers of bits, so the stored values can differ. Do not assume that casting a `double` value to `float` and then widening back to `double` will recover the lost precision.

### Narrowing Conversions and Overflow

`int` holds every `byte` and `short` value, but converting `int → byte`/`short` can drop bits:

```java
int number = 130;
byte narrowed = (byte) number;
System.out.println(narrowed); // -126
```

When you need to be sure a value is in range, compare against `Byte.MIN_VALUE` and `Byte.MAX_VALUE` **before casting**. For `int` or `long` arithmetic that can overflow, use `Math.addExact`, `Math.subtractExact`, or `Math.multiplyExact` when you need an error reported instead of silent wrap-around. Note that `Math.abs(Integer.MIN_VALUE)` can also be surprising because the mathematical absolute value of the negative bound cannot fit in an `int`.

### No Separate Primitive unsigned int/long

Java has no primitive `unsigned int` or `unsigned long` like C/C++. However, since Java 8 there have been methods supporting **unsigned interpretation** of `int`/`long` bits such as `Integer.toUnsignedString(...)`, `Integer.compareUnsigned(...)`, and `Long.divideUnsigned(...)`; `Byte.toUnsignedInt(...)` and `Short.toUnsignedInt(...)` help read 8/16 bits as unsigned numbers.

This **does not expand the storage range** of `int`/`long`: variables still retain the bit patterns and signed display behavior of their respective types, while certain operations/helpers interpret those bit patterns under unsigned conventions.

## 7. When to Choose Which Type?

| Scenario | Typically Appropriate Choice | Things to Check |
|---|---|---|
| Counters, array indices, integers within 32-bit range | `int` | Overflow, positive/negative range, concurrent operations |
| Integers exceeding `int` range but within 64-bit | `long` | `L` literals, overflow, and `long → double` conversion |
| File/buffer protocols with 8- or 16-bit fields | `byte`, `short` | Signed interpretation, masking, byte-level endianness |
| UTF-16 code units | `char` | Not identical to Unicode code point |
| Simulations/reals needing memory savings and tolerating low precision | `float` | Rounding error and accuracy needs |
| General floating-point math with higher binary precision | `double` | Rounding, NaN, infinity, approximate equality comparisons |
| Integers exceeding `long` range | `BigInteger` | CPU, RAM, digit count, operations producing huge results |
| Money/exact decimals with clear rounding rules | `BigDecimal` | Scale, precision, rounding mode, construction source |

`byte` or `short` does not automatically make all operations faster than `int`; arithmetic operations on `byte`/`short` are typically promoted to `int`. Choose types based on the data contract and storage requirements, not solely on a desire to "reduce bit count".

For currency, `BigDecimal` or an integer `long` representing the smallest unit can be appropriate depending on domain requirements. Only use `double` if the application **explicitly accepts** binary floating-point error and has suitable rounding/comparison rules.

## 8. Common Confusions When Reading Reference Tables

### Confusing Float.MIN_VALUE with the Lowest Negative Number

`Float.MIN_VALUE` is about `1.4E-45`, **positive and very close to 0**. If you want the finite negative number with the largest magnitude, use `-Float.MAX_VALUE`. The same applies to `Double.MIN_VALUE` and `-Double.MAX_VALUE`.

### Confusing Type Size with Object Size

`Integer.SIZE == 32` and `Integer.BYTES == 4` do not prove that a `new Integer(...)` or boxed `Integer` object occupies exactly 4 bytes of RAM. An object has a header and management overhead; arrays, references, alignment, and the JVM add further overhead. Moreover, creating wrappers via constructors is deprecated; use autoboxing or `Integer.valueOf` when a wrapper is needed.

### Confusing char with a Full Unicode Character

`char` has 16 bits, but a Unicode code point outside the BMP requires two UTF-16 code units. For strings containing emojis or supplementary characters, `String.length()` counts code units, which does not necessarily equal the number of Unicode code points or user-perceived characters.

### Confusing Float.MIN_EXPONENT with the Smallest Decimal Exponent

`MIN_EXPONENT` and `MAX_EXPONENT` state the **binary exponent range of normal numbers**, not the `E` exponent in `toString()`. Subnormal representations also contain positive numbers smaller than `MIN_NORMAL`, and decimal scientific notation is a separate formatting matter.

### Confusing Finite Range with Decimal Precision

`Double.MAX_VALUE` is huge, but that does not mean `double` represents every number from 0 up to that limit exactly. Floating-point values form a discrete set. As magnitude increases, the gap between consecutive values can exceed 1; that is why many nearby large integers yield the same result when cast to `double`.

### Confusing BigDecimal with Having No Limits at All

`BigDecimal` has an unscaled value of arbitrary magnitude, but `scale` still has type `int`; data and operations must fit within RAM/CPU and API rules. `MathContext` specifies result precision; it does not make operations with gigantic inputs resource-safe.

### Confusing the "Just Cast the Result" Rule

If two `int` operands multiply and overflow before being assigned to a `long`, writing `long answer = (long)(a*b)` does not recover the correct value. You must introduce `long` **before the multiplication**, such as `(long)a * b`. Similarly, `double ratio = 5 / 2` still receives `2.0`; use `5 / 2.0` if you want `2.5`.

## 9. Quick Reference Checklist and Self-Check

When you need to check a numeric value in code:

1. Identify the exact type of the **expression being evaluated**, not just the destination variable type.
2. For `byte`/`short`/`int`/`long`, get `MIN_VALUE`, `MAX_VALUE`, `SIZE`, and `BYTES` constants from the corresponding wrapper.
3. For `float`/`double`, distinguish **finite range**, **binary precision**, **subnormal**, `NaN`, and infinity.
4. For `char`, distinguish UTF-16 code unit from Unicode code point and cast to `int` only when you want to print the numeric code.
5. For `BigInteger`/`BigDecimal`, define business and resource limits; use `bitLength()`, `precision()`, and `scale()` as appropriate instead of asking for a fixed `SIZE`.
6. Before narrowing a type or multiplying/dividing integers, check whether data loss or overflow can occur.
7. Write boundary tests: values equal to `MAX_VALUE`, equal to `MIN_VALUE`, near 0, just outside the range (if applicable), and floating-point cases near precision boundaries.

**Self-Check 1:** Why is `Float.MIN_VALUE` positive while `Integer.MIN_VALUE` is negative? Because the two constants have different meanings: for `Integer`, it is the negative bound of a signed integer, whereas for `Float`, it is the smallest nonzero positive representable value in IEEE 754.

**Self-Check 2:** Can `char` hold the number `65535`, and does that mean it holds every Unicode character? It can hold the code unit value `65535`; **no**, a Unicode code point can lie outside the BMP and must be represented by a surrogate pair in UTF-16.

**Self-Check 3:** Can `long` represent every integer from `0` to `9_007_199_254_740_993`? **Yes**, because all of them are within the `long` range. However, `double` **cannot represent every integer exactly** in that interval: `2^53 + 1` is already an example that loses information when cast.

**Self-Check 4:** Does `BigInteger` have a `MAX_VALUE` like `Long.MAX_VALUE`? **No**. `BigInteger` has no fixed arithmetic bound at 64 bits; the practical limit lies in resources and implementation. The constant `BigInteger.TEN` is simply the number 10.

**Self-Check 5:** Does a `BigDecimal("123.4500")` with `precision = 7` and `scale = 4` occupy "7 bytes"? **No**. Precision is the number of significant decimal digits of the unscaled value, not byte storage size.

**Takeaway:** `byte/short/int/long` have fixed signed integer ranges; `char` is an unsigned 16-bit code unit; `float/double` have finite bounds, limited binary precision, and special values; `BigInteger/BigDecimal` have flexible magnitude/precision but are not exempt from resource limits. Always look up constants by **specific type and meaning**, especially noting that `Float.MIN_VALUE`/`Double.MIN_VALUE` differ from how `MIN_VALUE` is understood for integers.
