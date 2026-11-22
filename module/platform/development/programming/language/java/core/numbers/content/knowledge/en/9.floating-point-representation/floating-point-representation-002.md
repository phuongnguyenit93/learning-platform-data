# Sign Bit, Exponent, and Fraction in Java Floating-Point Representation

## 1. Objective: Understanding How `float`/`double` Numbers Are Stored

`float` and `double` in Java do not store a decimal number as a string of digits like `"5.75"`. They represent numbers in **sign, binary exponent, and significand** form using a finite number of bits. Understanding this structure explains why `0.1` is not represented exactly, why `-0.0` can differ from `+0.0` at the bit level, and why some operations yield `Infinity` or `NaN`.

This lesson belongs to the **Floating-Point Representation** group in Java Core — Numbers. After completing it, you should be able to:

1. Identify the **sign**, **biased exponent**, and **fraction field** in a 32-bit `float` and a 64-bit `double`.
2. Compute the actual exponent from the stored exponent using **bias 127** (binary32) or **1023** (binary64).
3. Decode **normal** values using the implicit leading `1` bit before the fraction, and distinguish them from **subnormal** values that lack the implicit `1` bit.
4. Correctly recognize **±0.0**, **±Infinity**, **NaN**, and finite-number boundaries.
5. Use `Float.floatToRawIntBits`, `Double.doubleToRawLongBits`, and bitmasks to inspect bit patterns in Java 17+.
6. Distinguish **bit pattern**, **mathematical value**, **string output formatting**, and **calculation precision**.

Prerequisites: binary numbers and powers of 2, `&`, unsigned right shift `>>>`, hex literals `0x...`, `int`/`long` and `float`/`double` types. This lesson uses IEEE 754 binary32/binary64 structure and the Java SE 17 API.

## 2. The Three Bit Fields of a Floating-Point Number

### 2.1. Layout Overview

**`float` (binary32)** has exactly 32 bits:

```text
bit index: 31 | 30................23 | 22..........................0
           S | E E E E E E E E    | F F F F F F F F F F F F F F F F F F F F F F F
width:     1 |        8           |                     23
```

**`double` (binary64)** has exactly 64 bits:

```text
bit index: 63 | 62................52 | 51...........................................0
           S  | E (11 bits)         | F (52 bits)
width:     1  |         11          |                    52
```

Field `S` is the **sign bit**; field `E` is the **stored/biased exponent**; field `F` is the **fraction bits** or **trailing significand field**. The term “mantissa” is sometimes used in older literature, but you should clearly distinguish the **stored fraction bits** from the **actual significand**, which may include an implicit leading bit.

| Property | `float` | `double` |
| --- | ---: | ---: |
| Total length | 32 bits | 64 bits |
| Sign bit | 1 | 1 |
| Exponent field | 8 bits | 11 bits |
| Fraction field | 23 bits | 52 bits |
| Bias | 127 | 1023 |
| Normal significand precision, including implicit leading bit | 24 bits | 53 bits |
| Unbiased exponent of normal numbers | −126 to +127 | −1022 to +1023 |
| Stored exponent values reserved for special cases | 0 and 255 | 0 and 2047 |

Use `int` to hold all bits of a `float` and `long` to hold all bits of a `double`. If you print these values in **signed decimal**, a bit pattern with the top bit set can look like a negative integer; to see the structure clearly, print in fixed-width hexadecimal.

### 2.2. What Does the Sign Bit Mean?

For nonzero finite numbers and infinities:

- `S = 0` means positive sign;
- `S = 1` means negative sign.

You can think of the sign factor as `(-1)^S`. For instance, `+6.5` and `-6.5` have identical exponent/fraction fields, differing only in the sign bit.

**Note:** the sign bit is also present on `+0.0`, `-0.0`, and NaN patterns. You must not treat the sign of a NaN as “a negative NaN with a negative numeric value” in ordinary numeric comparisons; NaN does not participate in numeric ordering like finite numbers.

## 3. Normal Numbers: Decoding from Exponent and Fraction

When the stored exponent field is **neither 0 nor all 1-bits**, the value is called **normal (normalized)**.

Value formula:

```text
normal = (-1)^S × (1 + F / 2^p) × 2^(E - bias)
```

Where:

- `S`: sign bit, 0 or 1.
- `E`: unsigned integer obtained by reading the entire exponent field.
- `F`: unsigned integer obtained by reading the entire fraction field.
- `p`: number of fraction bits, equal to `23` for `float` and `52` for `double`.
- `bias`: `127` for `float`, `1023` for `double`.

**Meaning of the implicit `1` bit:** for normal numbers, the significand has the binary form `1.fraction_bits`. The leading `1` bit does not need to be stored in the fraction field, yielding 24 bits of precision from 23 stored bits in `float`, or 53 bits of precision from 52 stored bits in `double`.

For example, a `float` binary fraction `0111000...` means:

```text
1.0111₂ = 1 + 0/2 + 1/4 + 1/8 + 1/16 = 1.4375
```

Do not read `E` directly as the actual exponent; you must **subtract the bias**. For example, a `float` with `E = 129` has an actual exponent of `129 - 127 = 2`. A `double` with `E = 1025` has an actual exponent of `1025 - 1023 = 2`.

### 3.1. Step-by-Step Decoding Example: `5.75f`

Convert `5.75` to binary:

```text
5      = 101₂
0.75   = 0.11₂
5.75   = 101.11₂
       = 1.0111₂ × 2²
```

The sign field is `0` because the number is positive. The actual exponent is `e = 2`, so the stored exponent for `float` is `2 + 127 = 129 = 10000001₂`. The fraction consists of the bits after the binary point in `1.0111₂`: `01110000000000000000000₂` (23 bits), which equals `0x380000`.

Assemble all 32 bits:

```text
sign       exponent       fraction
 0         10000001       01110000000000000000000
```

The 32-bit sequence equals `0x40B80000`. Verify with the formula:

```text
S = 0
E = 129
F / 2²³ = 0.4375
value = (+1) × (1 + 0.4375) × 2² = 5.75
```

Because `0.75 = 3/4` has a finite binary representation, `5.75` is stored exactly here.

### 3.2. Decoding Example: `-6.5` as `double`

`6.5 = 110.1₂ = 1.101₂ × 2²`.

- Sign `S = 1`.
- Unbiased exponent `e = 2`.
- Stored exponent `E = 2 + 1023 = 1025`.
- Fraction `.101₂ = 1/2 + 1/8 = 0.625`; the 52-bit fraction corresponds to hex `0xA000000000000`.
- Full `double` bit pattern: `0xC01A000000000000`.

Check: `(-1) × (1 + 0.625) × 4 = -6.5`.

## 4. Stored Exponents Do Not Use All Codes for Normal Numbers

The exponent values `E = 0` and `E = all 1-bits` are reserved for special meanings:

| Exponent Field | Fraction Field | Classification | Interpretation |
| --- | --- | --- | --- |
| `0 < E < EmaxStored` | Any | Normal | `1.fraction × 2^(E − bias)` with sign |
| `E = 0` | `F = 0` | Zero | `+0.0` or `-0.0` depending on sign |
| `E = 0` | `F != 0` | Subnormal | `0.fraction × 2^(1 − bias)` with sign |
| `E = EmaxStored` | `F = 0` | Infinity | `+∞` or `−∞` depending on sign |
| `E = EmaxStored` | `F != 0` | NaN | “Not a Number”, not an ordered number |

For `float`, `EmaxStored = 255`; for `double`, `EmaxStored = 2047`. Do not confuse the **maximum stored E value** with the **maximum unbiased normal exponent** (`127` or `1023`).

It is also incorrect to say “exponent 0 is always 2⁻¹²⁷” and plug it into the normal formula: when `E=0`, both zero and subnormals follow separate rules, explained next.

## 5. Subnormals: Numbers Too Small to Represent in Normal Form

**Subnormal** numbers (formerly called denormals) use `E = 0` and `F != 0`. They have no implicit leading `1` bit; the significand is interpreted as `0.fraction_bits`.

Formula:

```text
subnormal = (-1)^S × (F / 2^p) × 2^(1 - bias)
```

For `float`, `1 - bias = -126`; for `double`, it is `-1022`.

Why do we need subnormals? Between the smallest positive normal number and `+0.0`, there remain many representable positive values in subnormal form. This is the **gradual underflow** mechanism — precision degrades gradually as values approach zero, instead of jumping abruptly from the smallest normal directly to zero.

### 5.1. `float` Milestones

- `Float.MIN_NORMAL` = `2⁻¹²⁶`, the **smallest positive normal**: bits `0x00800000`.
- `Float.MIN_VALUE` = `2⁻¹⁴⁹`, the **smallest positive subnormal**: bits `0x00000001`.
- The largest positive subnormal has bits `0x007FFFFF` and lies immediately below `Float.MIN_NORMAL`.

**The name `MIN_VALUE` can be misleading:** it is the **smallest nonzero positive** value, not the smallest negative number; for the finite negative number with the largest magnitude, see `-Float.MAX_VALUE`.

### 5.2. `double` Milestones

- `Double.MIN_NORMAL` = `2⁻¹⁰²²`; bits `0x0010000000000000`.
- `Double.MIN_VALUE` = `2⁻¹⁰⁷⁴`; bits `0x0000000000000001`.
- Largest positive subnormal: `0x000FFFFFFFFFFFFF`.

**Key takeaway:** `MIN_NORMAL` and `MIN_VALUE` are vastly different in magnitude; merely remembering “double is accurate to 15 digits” is not enough to understand underflow. Relative accuracy of subnormals is much poorer than that of normal numbers, yet they still represent exact discrete levels in the very small range.

### 5.3. Computing the Value of the Smallest Subnormal

For `float`, pick `S=0`, `E=0`, `F=1`. By the formula:

```text
value = (1 / 2²³) × 2⁻¹²⁶
      = 2⁻¹⁴⁹
      = Float.MIN_VALUE
```

Do not use `(1 + F / 2²³)` as with normal numbers. Including an implicit `1` bit would produce the wrong value at `E = 0`.

## 6. Signed Zero: `+0.0` and `-0.0`

In binary32:

```text
+0.0f = 0x00000000
-0.0f = 0x80000000
```

In binary64:

```text
+0.0  = 0x0000000000000000
-0.0  = 0x8000000000000000
```

Both have `E = 0`, `F = 0`; they differ only in `S`.

In arithmetic comparison:

```java
System.out.println(0.0 == -0.0); // true
```

However, they remain **two distinct bit patterns** and can behave differently in certain operations:

```java
System.out.println(1.0 / 0.0);  // Infinity
System.out.println(1.0 / -0.0); // -Infinity
```

Therefore, you need to determine whether you are comparing **numeric values**, **bit patterns**, or **wrapper total ordering**. `Double.compare(0.0, -0.0)` returns a positive result (it distinguishes the sign of zero), whereas `0.0 == -0.0` is `true`. This is not a contradiction, but rather different comparison contracts.

## 7. Infinity and NaN: When the Exponent Is All 1-Bits

### 7.1. Infinity

For `float`, `E=255`, `F=0`:

```text
+Infinity  0x7F800000
-Infinity  0xFF800000
```

For `double`, `E=2047`, `F=0`:

```text
+Infinity  0x7FF0000000000000
-Infinity  0xFFF0000000000000
```

`Float.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY` are API constants. Floating-point division such as `1.0 / 0.0` produces infinity, unlike `int` division by `0` which throws `ArithmeticException`.

### 7.2. NaN

With `E` all 1-bits **and** `F != 0`, the bit pattern represents `NaN`.

- NaN has many different **bit patterns**, not just one unique bit sequence.
- The sign bit can be 0 or 1, but that does not turn NaN into an ordinary positive/negative numeric value.
- `Double.NaN` and `Float.NaN` are constants representing NaN; there is no primitive literal named `NaN`.
- Under floating-point comparison `==`, `NaN == NaN` is `false`. To test for it, call `Float.isNaN` or `Double.isNaN`.

`Float.floatToIntBits` and `Double.doubleToLongBits` **canonicalize NaN** when extracting bits: NaNs are normalized to a canonical pattern (`0x7FC00000` for `float` and `0x7FF8000000000000` for `double`).

If you need to inspect the **raw bits** of a NaN, use `Float.floatToRawIntBits` or `Double.doubleToRawLongBits`. However, some signaling NaNs may be converted to quiet NaNs when passed through hardware or operations; you should not promise an exact bit round-trip for every NaN payload across all platforms.

### 7.3. Classifying from E and F Alone

The classification rule can be written as follows:

```text
if E == 0:
    if F == 0: ZERO
    else:      SUBNORMAL
else if E == maximum exponent code:
    if F == 0: INFINITY
    else:      NaN
else:
    NORMAL
```

This is **pseudocode**, not standalone Java. Its meaning depends on the exact exponent/fraction field widths of `float` or `double`.

## 8. Inspecting Bit Patterns in Java Instead of Guessing from Strings

Standard APIs to know:

| Type | Read Bits | Reconstruct Value | Notes |
| --- | --- | --- | --- |
| `float` | `Float.floatToRawIntBits(value)` | `Float.intBitsToFloat(bits)` | Returns/accepts 32-bit `int` |
| `float` | `Float.floatToIntBits(value)` | `Float.intBitsToFloat(bits)` | Canonicalizes NaN |
| `double` | `Double.doubleToRawLongBits(value)` | `Double.longBitsToDouble(bits)` | Returns/accepts 64-bit `long` |
| `double` | `Double.doubleToLongBits(value)` | `Double.longBitsToDouble(bits)` | Canonicalizes NaN |

**Do not use a primitive cast `(int) someFloat` to get bits!** That cast converts the **numeric value** to an integer according to narrowing rules, which is completely different from reinterpreting bits.

Example:

```java
float value = 5.75f;
int truncatedValue = (int) value;             // 5
int rawBits = Float.floatToRawIntBits(value); // 0x40B80000
```

From the same `float` variable, two `int` values have completely different meanings: one is a value conversion result, and the other is a **bit encoding**.

### 8.1. Runnable Example: Extracting `float` Sign/Exponent/Fraction

Save as **`FloatFields.java`**:

```java
public class FloatFields {
    public static void main(String[] args) {
        float value = 5.75f;
        int bits = Float.floatToRawIntBits(value);

        int sign = (bits >>> 31) & 1;
        int exponent = (bits >>> 23) & 0xFF;
        int fraction = bits & 0x7FFFFF;

        System.out.printf("%08X%n", bits);
        System.out.println(sign);
        System.out.println(exponent);
        System.out.printf("%06X%n", fraction);
        System.out.println(Float.intBitsToFloat(bits));
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 FloatFields.java
java FloatFields
```

**Exact stdout:**

```text
40B80000
0
129
380000
5.75
```

Explanation of the extraction operations:

- `>>> 31` shifts the sign bit to the lowest position, and `& 1` keeps one bit.
- `>>> 23` shifts the 8 exponent bits to the lowest positions, and `& 0xFF` masks that exact field.
- `& 0x7FFFFF` keeps the lower 23 fraction bits.
- `printf("%08X%n", bits)` prints 8 hex digits (32 bits); `%06X` prints the fraction with at least 6 hex digits.
- `Float.intBitsToFloat(bits)` reinterprets the exact bit pattern back to `5.75`.

With `float`, a negative sign or certain NaN patterns can cause `bits` to be a negative `int` when read in base 10. That is a **signed-integer interpretation artifact** of the bit pattern; it does not mean the `float` variable itself was coerced to a directly related negative integer value.

### 8.2. Runnable Example: Extracting `double` Fields

Save as **`DoubleFields.java`**:

```java
public class DoubleFields {
    public static void main(String[] args) {
        double value = -6.5;
        long bits = Double.doubleToRawLongBits(value);

        long sign = (bits >>> 63) & 1L;
        long exponent = (bits >>> 52) & 0x7FFL;
        long fraction = bits & 0x000F_FFFF_FFFF_FFFFL;

        System.out.printf("%016X%n", bits);
        System.out.println(sign);
        System.out.println(exponent);
        System.out.printf("%013X%n", fraction);
        System.out.println(Double.longBitsToDouble(bits));
    }
}
```

Run:

```bash
javac --release 17 DoubleFields.java
java DoubleFields
```

**Exact stdout:**

```text
C01A000000000000
1
1025
A000000000000
-6.5
```

In `double`, the fraction has 52 bits = 13 hex digits; the exponent has 11 bits so the mask is `0x7FFL`. The `L` suffix on the 64-bit mask literals makes the `long` arithmetic explicit. Even if raw `bits` is negative when read as a `long`, the logical shift `>>>` and masks still extract each field accurately.

## 9. Runnable Example: Special Bit Patterns

Save as **`SpecialFloatingBits.java`**:

```java
public class SpecialFloatingBits {
    public static void main(String[] args) {
        System.out.printf("%08X%n",
                Float.floatToRawIntBits(-0.0f));
        System.out.printf("%08X%n",
                Float.floatToRawIntBits(Float.MIN_VALUE));
        System.out.printf("%08X%n",
                Float.floatToRawIntBits(Float.MIN_NORMAL));
        System.out.printf("%08X%n",
                Float.floatToRawIntBits(Float.POSITIVE_INFINITY));

        System.out.printf("%016X%n",
                Double.doubleToRawLongBits(-0.0));
        System.out.println(0.0 == -0.0);
        System.out.println(Double.isNaN(0.0 / 0.0));
        System.out.println(Double.isInfinite(1.0 / 0.0));
        System.out.printf("%08X%n",
                Float.floatToIntBits(Float.intBitsToFloat(0x7FC01234)));
    }
}
```

Run:

```bash
javac --release 17 SpecialFloatingBits.java
java SpecialFloatingBits
```

**Exact stdout:**

```text
80000000
00000001
00800000
7F800000
8000000000000000
true
true
true
7FC00000
```

The first four `float` lines are **−0.0**, **smallest positive subnormal**, **smallest positive normal**, and **+Infinity**. The next `double` pattern is **−0.0**. The two zero values compare equal under `==` despite having different bits. Dividing `0.0/0.0` produces NaN; `1.0/0.0` produces infinity. The last line shows `Float.floatToIntBits` canonicalizing multiple NaN bit patterns to `0x7FC00000`.

The code uses `Float.intBitsToFloat(0x7FC01234)` to construct a NaN by bits; avoid interpreting the integer `0x7FC01234` as a real decimal value via casting.

## 10. Precision: Why the Fraction Field Does Not Mean Enough Decimal Digits

For normal numbers:

- `float`: **24 bits** of significand precision (23 stored fraction bits + 1 implicit `1` bit).
- `double`: **53 bits** of precision (52 fraction bits + 1 implicit `1` bit).

This means `float` distinguishes every integer in the range from `-2²⁴` to `+2²⁴` when represented exactly; specifically, `2²⁴ + 1` has no distinct `float` representation from `2²⁴` under round-to-nearest, ties-to-even. Similarly, `double` represents every integer up to magnitude `2⁵³` exactly, but does not preserve all integers above that threshold.

Self-verifiable example:

```java
int bigFloatInt = 16_777_216; // 2^24
boolean floatEqual = (float) bigFloatInt
        == (float) (bigFloatInt + 1); // true

long bigDoubleLong = 9_007_199_254_740_992L; // 2^53
boolean doubleEqual = (double) bigDoubleLong
        == (double) (bigDoubleLong + 1); // true
```

This does not mean `float` can only store values up to `2²⁴` or `double` only up to `2⁵³`: their magnitude ranges are vastly wider thanks to the exponent. It simply means **the spacing between representable numbers increases as the exponent increases**. Therefore:

- The exponent field primarily determines the **magnitude scale**.
- The significand/fraction field determines the **step size and relative precision** within each binade.
- For subnormals, relative precision decreases gradually as values approach 0.

### 10.1. Why Is `0.1` Rounded?

`0.1₁₀` has an infinite repeating binary representation. Because the number of fraction bits is finite, `float`/`double` store an approximate value after rounding:

```java
double x = 0.1 + 0.2;
System.out.println(x);        // 0.30000000000000004
System.out.println(x == 0.3); // false
```

This is a consequence of the sign/exponent/significand structure, not a `println` bug. If a problem requires **business-exact decimal arithmetic** (such as currency), consider `BigDecimal` initialized from strings and explicit rounding rules; `BigDecimal` does not use the same binary32/binary64 structure as `float`/`double`.

### 10.2. Spacing Between Consecutive Numbers (ULP)

`Math.ulp(x)` returns the size of one **unit in the last place** of the argument in the corresponding floating-point format. Near `1.0f`, the step to the next `float` is `2⁻²³`; near `1.0` as a `double`, the upward step is `2⁻⁵²`. However, in the neighborhood of a power-of-2 boundary, the spacing below can differ from the spacing above; you should not treat a single fixed epsilon as valid across all value scales.

`Math.nextUp(x)`/`Math.nextDown(x)` can be used when you need to step through adjacent representable floating-point numbers. They are useful for boundary testing, though they do not replace choosing error criteria appropriate for the problem domain.

## 11. From Hex Floating-Point Literals Back to the Three Bit Fields

Java supports literals of the form `0x...p...`, where `p` marks the **base-2 exponent**. For example:

```java
float a = 0x1.7p2f;    // 1.4375 × 2² = 5.75
double b = -0x1.ap2;   // -(1.625 × 2²) = -6.5
```

`0x1.7p2` has a direct arithmetic meaning close to the normalized binary form `1.0111₂ × 2²`. You can cross-check hex literals with `Float.toHexString` or `Double.toHexString` when you want to read the significand/exponent in powers of 2:

```java
System.out.println(Float.toHexString(5.75f)); // 0x1.7p2
System.out.println(Double.toHexString(-6.5)); // -0x1.ap2
```

**Important:** the string produced by `toHexString` is a **value representation**, not a direct printout of each raw bit field. For subnormal numbers, `toHexString` uses a representation suited to the subnormal range; to inspect individual exponent/fraction bits, use the raw-bits APIs and masks shown above.

## 12. Distinguishing IEEE 754 Bit Layout from Memory Byte Order

A `float` is defined as having 32 value bits; this alone does not dictate in what order its four bytes appear in a file, network packet, or `ByteBuffer`.

- **Bit layout** specifies which bits are sign/exponent/fraction when indexing a 32/64-bit pattern.
- **Endianness** specifies the **byte** order when storing that same bit pattern into memory or a byte stream. Big-endian and little-endian can produce different byte orders, even though the sign/exponent/fraction fields of the value do not change.
- `ByteBuffer` has a byte-order policy that can be configured via `order(ByteOrder.BIG_ENDIAN)` or `LITTLE_ENDIAN`.

For example, the pattern for `5.75f` is `0x40B80000`. When writing 4 bytes:

```text
big-endian:    40 B8 00 00
little-endian: 00 00 B8 40
```

This is an example of **byte order for the same bit pattern**, not two different floating-point values. When exchanging data between systems, the contract must specify both the numeric format and the byte order.

## 13. Common Misconceptions and Pitfalls

1. **“23 fraction bits means float has 23-bit precision.”** For normal numbers, there is an implicit `1` bit, so significand precision is **24 bits**.
2. **“The stored exponent is the actual exponent.”** You must subtract the **bias** for normal numbers; `E = 129` in `float` corresponds to `e = 2`.
3. **“Exponent 0 is a normal number with exponent -127.”** Wrong. `E=0` is reserved for zero/subnormal and uses a separate formula with `1-bias`.
4. **“`Float.MIN_VALUE` is the smallest negative number.”** Wrong. It is the **smallest nonzero positive number**, a subnormal.
5. **“`~` or casting `(int)` extracts the exact bits of a floating-point number.”** Wrong. A cast converts the value rather than reading the bit encoding; use `Float.floatToRawIntBits`/`Double.doubleToRawLongBits`.
6. **“`-0.0` and `+0.0` are identical in every way.”** They are equal under `==`, yet have different sign bits and can yield opposite-signed infinities upon division.
7. **“Every NaN always has the same bit pattern.”** There are many NaN patterns; `floatToIntBits`/`doubleToLongBits` canonicalize them.
8. **“`0.1` is stored exactly because many decimal digits are displayed.”** A finite binary significand cannot represent 1/10 exactly; the displayed string is a presentation layer.
9. **“The exponent is the number of digits after the decimal point.”** It is a **base-2** power, completely different from `BigDecimal`'s decimal scale.
10. **“Bit layout determines byte order.”** No. Endianness must be specified when serializing bytes.
11. **“A number with sign bit 1 is always a finite negative number.”** That pattern could be `-0.0`, `-Infinity`, or NaN.
12. **“Normal and subnormal forms share the same implicit leading bit.”** For subnormals, the significand is `0.fraction`, not `1.fraction`.

## 14. Practice Exercises with Answers

### Exercise 1 — Field Positions

State the sign bit, number of exponent bits, and number of fraction bits for `float` and `double`.

**Answer:** `float` consists of `1 + 8 + 23 = 32` bits; `double` consists of `1 + 11 + 52 = 64` bits.

### Exercise 2 — Bias

For a normal `float` with `E=130`, what is the actual exponent? What about a normal `double` with `E=1025`?

**Answer:** `130−127=3` and `1025−1023=2`. You must subtract the corresponding bias.

### Exercise 3 — Decoding `5.75f`

Given the bit pattern `0x40B80000`, extract `S`, `E`, and `F`, then compute the value back.

**Answer:** `S=0`, `E=129`, `F=0x380000`. Fraction = `0.4375`; value = `(1+0.4375)×2²=5.75`.

### Exercise 4 — Distinguishing 0 and Subnormal

The two `float` patterns `0x00000000` and `0x00000001` have the same exponent field. Are they the same?

**Answer:** No. `E=0,F=0` is `+0.0`; `E=0,F=1` is the smallest positive subnormal `2⁻¹⁴⁹`.

### Exercise 5 — Identifying Infinity and NaN

For `float`, what does `E=255`, `F=0` represent? What does `E=255`, `F=1` represent?

**Answer:** The first case is infinity with the sign determining ±; the second case is NaN because the fraction is nonzero. Do not place NaN into normal arithmetic ordering.

### Exercise 6 — Sign of Zero

Why is `0.0 == -0.0` true while `Double.doubleToRawLongBits(0.0)` and `Double.doubleToRawLongBits(-0.0)` differ?

**Answer:** The `==` operator compares floating-point values numerically; raw bits include the sign bit. The two zeros have different sign bits.

### Exercise 7 — Cast or Raw Bits?

Given `float f=5.75f`, what do `(int)f` and `Float.floatToRawIntBits(f)` produce?

**Answer:** The cast produces `5`; raw-bits produces the pattern `0x40B80000` (which, if printed as a decimal `int`, is a large integer). They serve different purposes.

### Exercise 8 — Decimal vs Binary Precision

Why is `0.1 + 0.2 == 0.3` false when using `double`?

**Answer:** 1/10 and 1/5 have repeating binary representations and are rounded to the binary64 value set; the rounded sum does not necessarily match the binary64 pattern of the literal 0.3.

### Exercise 9 — Changing Endianness

Which 4 bytes correspond to the `float` pattern `0x40B80000` in big-endian and little-endian?

**Answer:** `40 B8 00 00` and `00 00 B8 40`. The float value does not change; only the byte order does.

### Exercise 10 — Large Integers and Representation Spacing

Why can `(float)16_777_216` equal `(float)16_777_217` even though the two `int` values are different?

**Answer:** binary32 has 24 bits of significand precision and lacks enough bits to distinguish every integer at scales beyond `2²⁴`; the adjacent value can be rounded to the same pattern.

## 15. Checklist and Official Documentation

- [ ] I correctly identify **sign/exponent/fraction bits** for binary32 and binary64.
- [ ] I do not confuse the stored fraction field with the entire normal significand.
- [ ] I know biases `127` and `1023`, and the unbiased normal exponent limits.
- [ ] I can write the decoding formulas for **normal** and **subnormal** numbers.
- [ ] I distinguish zero, subnormal, normal, infinity, and NaN from `E` and `F`.
- [ ] I can explain why `-0.0` differs from `+0.0` in raw bits, even though `==` is true.
- [ ] I can use `floatToRawIntBits` and `doubleToRawLongBits` without confusing them with value casts.
- [ ] I understand NaN canonicalization and the risk of round-tripping signaling NaNs.
- [ ] I do not infer precision from the number of digits printed by `println`.
- [ ] I know byte order is a separate concern when reading/writing the bytes of a bit pattern.
- [ ] I ran all three programs and verified the exact hex/value outputs.

**Official documentation for Java 17:**

- [Java Language Specification, `4.2.3 Floating-Point Types, Formats, and Values`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3) — floating-point semantics.
- [Java SE 17 Float API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html) — bit layout, `floatToIntBits`, `floatToRawIntBits`, `intBitsToFloat`.
- [Java SE 17 Double API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html) — `doubleToLongBits`, `doubleToRawLongBits`, `longBitsToDouble`.
- [Java SE 17 Math API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html) — `ulp`, `nextUp`, `nextDown`.
- [Java SE 17 ByteBuffer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html) — byte order and working with binary data.

An effective way to read a `float`/`double` is: **read the sign, decode the exponent, choose the normal/subnormal formula or identify a special case, and then interpret the fraction in base 2**. Once these fields are understood, many “strange” floating-point phenomena become explainable and verifiable consequences.