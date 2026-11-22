# Hexadecimal Floating-Point Literals in Java

> **Java core – numbers / Literals and Bases**  
> Goal: read and write hexadecimal floating-point literals yourself, calculate their values by hand, distinguish them from base-16 integer literals and decimal floating-point numbers, and understand the benefit of power-of-2 notation when inspecting `float`/`double`.

## 1. Concept and Motivation

Java supports **hexadecimal floating-point literals**: writing a `float` or `double` value in source code using a **base-16 significand** and a **base-2 exponent**. Example:

```java
double a = 0x1.8p1;   // 3.0
double b = 0x1.0p-2;  // 0.25
float  c = 0x1.Ap2f;  // 6.5f
```

The key point lies in the letter **`p`**: it separates the *significand* from the binary exponent. Even though the significand is written in base-16 digits, the exponent after `p` denotes a **power of 2**, not a power of 16. This syntax has been supported in Java since Java 5 and still works in Java 17+.

Because `float` and `double` store numbers in **binary** floating-point format (IEEE 754), this hex notation is especially useful to:

- describe an exact, reproducible binary value in source code;
- write boundaries, `2^k` constants, and bit-adjacent values;
- examine rounding and the difference between a `double` value and its decimal display on screen;
- read the output of `Double.toHexString` and `Float.toHexString` when debugging calculations.

These are still literals for **`float`/`double`**; they have nothing to do with two's complement of negative integers, are not `BigDecimal` syntax, and do not automatically create an infinite-precision numeric type.

## 2. Syntax: `0x...p...` and Type Suffixes

An easy-to-remember general form:

```text
[+|-]  0x<hex-significand> p<decimal-exponent> [f|F|d|D]
       └── base-16 digits ─┘   └─── base-10 digits, power of 2 ────┘

Example: 0x1.8p+1
         |  |  | |
         |  |  | +-- exponent +1, meaning multiply by 2^1
         |  |  +---- p: marker starting the binary exponent
         |  +------- 1.8: hex significand, equivalent to 1 + 8/16
         +---------- 0x: identifies base 16
```

Components:

1. **Prefix** `0x` or `0X`: signals a base-16 significand.
2. **Significand** consisting of digits `0–9` and `A–F`/`a–f`; may contain a dot `.` separating the integer and fractional parts in base 16. At least one hex digit is required.
3. **`p` or `P` is mandatory** in a hex floating-point literal; immediately following it is a decimal exponent that may have a `+`/`-` sign. The exponent digits must be `0–9`.
4. **Suffix** `f`/`F` gives the literal type `float`; `d`/`D` or no suffix gives the literal type `double`.
5. A leading `-` at the start of the expression is the **unary minus operator**, not part of the literal's digits. This rarely affects everyday use, but is important in how Java parses syntax.

Valid ways to write them:

```java
double one       = 0x1p0;        // 1.0: no decimal point needed
double half      = 0x.8p0;       // 0.5: no digit needed before decimal point
double two       = 0x1.p1;       // 2.0: no digit needed after decimal point
double six       = 0X1.8P+2D;    // 6.0: uppercase is also valid
float eighth     = 0x1p-3F;     // 0.125f
double sixteen   = 0x1_0p0;     // 16.0: _ placed between digits
```

The letter `E`/`e` in the significand **is a base-16 digit with value 14**, not an exponent marker. In `0x1.ep3`, `e` belongs to the significand, while `p3` is the exponent. Similarly, the `F`/`f` suffix is only interpreted as a type suffix when placed **after the entire exponent**; an `f` appearing before `p` is the base-16 digit with value 15.

## 3. Value Calculation Formula

Write the base-16 significand as `H` and the integer exponent after `p` as `E`. The mathematical value before rounding to `float`/`double` is:

\[
\boxed{\text{Value} = H_{16}\times 2^E}
\]

Example `0x1.8p1`:

- `0x1.8` = `1 + 8/16 = 1.5` (in decimal).
- `p1` means multiply by `2^1 = 2`.
- Result: `1.5 × 2 = 3.0`.

For a significand with multiple digits after the dot, the digit immediately after the dot has weight `16^(-1)`, the second digit has weight `16^(-2)`, and so on.

Example `0xA.Cp-2`:

\[
0xA.C=10+\frac{12}{16}=10.75
\]

\[
0xA.Cp-2=10.75\times 2^{-2}=10.75/4=2.6875
\]

Reference table:

| Literal | Significand in Decimal | Factor `2^E` | Value |
| --- | ---: | ---: | ---: |
| `0x1p0` | 1 | 1 | 1.0 |
| `0x1.8p1` | 1.5 | 2 | 3.0 |
| `0x1.8p-1` | 1.5 | 0.5 | 0.75 |
| `0x1p-4` | 1 | 1/16 | 0.0625 |
| `0xFp-4` | 15 | 1/16 | 0.9375 |
| `0x1.Ap2` | 1.625 | 4 | 6.5 |
| `0xA.Cp-2` | 10.75 | 1/4 | 2.6875 |
| `0x1.2p3` | 1.125 | 8 | 9.0 |
| `0x1_0.8p+2` | 16.5 | 4 | 66.0 |

**Do not confuse with a power of 16.** If `p1` meant multiplying by 16, `0x1.8p1` would become 24; Java specifies that it equals **3** because `p1` multiplies by 2.

## 4. Why Is Base 16 Paired with Powers of 2?

One hex digit corresponds to exactly **4 binary bits**:

```text
hex:   1   .   8
bits:  0001 . 1000
           = 1 + 1/2 = 1.5

0x1.8p1:
1.1 (binary) × 2^1 = 11.0 (binary) = 3.0
```

Another example: the base-10 number `10.625` is `1010.101` in base 2. We can write:

```text
10.625 (decimal)
= 1010.101 (binary)
= 0xA.Ap0  (A + A/16 = 10 + 10/16)
= 0x1.54p3 (1 + 5/16 + 4/256) × 8
```

Both `0xA.Ap0` and `0x1.54p3` represent `10.625`. The form `0x1.54p3` has a significand starting with `1`, close to the **normalized** display format that Java APIs typically produce for finite *normal* floating-point numbers.

For numbers representable with a finite number of binary digits, hex is very convenient: e.g., `1/8 = 2^(-3) = 0x1p-3`. Conversely, `0.1` in base 10 cannot be represented with finitely many binary digits; to write the **`double` value closest to 0.1**, a rounded binary pattern is needed.

## 5. Distinguishing Hex Integer Literals from Hex Floating-Point Literals

`0x...` by itself is **not enough** to make a floating-point literal. The `pE` part makes the difference:

| Source Code | Literal Type | Value |
| --- | --- | --- |
| `0x10` | `int` | 16 |
| `0x10L` | `long` | 16 |
| `0x10p0` | `double` | 16.0 |
| `0x10p0f` | `float` | 16.0f |
| `0x1Ap0` | `double` | 26.0 |
| `0x1e3` | `int` | 483 (`0x1E3`) |
| `0x1e3p0` | `double` | 483.0 |
| `0x1.8p1` | `double` | 3.0 |

A subtle point: `double value = 0x10;` compiles because Java converts `int 16` to `double 16.0` on assignment. **`0x10` itself is still an integer literal**. In contrast, `0x10p0` is a floating-point literal from the start.

Common invalid syntax forms:

```java
// DOES NOT compile: significand has a dot but lacks exponent p...
// double wrong1 = 0x1.8;

// DOES NOT compile: e cannot replace p in a hex literal
// double wrong2 = 0x1.8e2;

// DOES NOT compile: assigning a double literal to float without a cast/suffix
// float wrong3 = 0x1.8p1;
```

The right ways are `0x1.8p0` for `1.5`; `0x1.8p1` for `3.0`; and `0x1.8p1f` for `float 3.0f`. When you want `float`, write the `f`/`F` suffix or perform an intentional cast, keeping rounding in mind.

## 6. Suffixes, Underscores, and Negative Exponents

Suffix syntax has the same meaning as in decimal floating-point literals:

```java
double d1 = 0x1.4p2;   // 5.0, default double
double d2 = 0x1.4p2D;  // 5.0, explicit double
float f1 = 0x1.4p2f;   // 5.0f, float
float f2 = 0X1.4P+2F;  // 5.0f, uppercase valid
```

Exponent `p-4` means multiplying by `2^(-4)`, **not** a "negative significand"; the sign of the overall value still depends on the sign at the start of the expression.

```java
double x = 0x1p-4;   // +0.0625
double y = -0x1p-4;  // -0.0625
```

`_` is used to group digits just like in other numeric literals, but must be placed **between digits** of the significand or the exponent, not at arbitrary positions.

```java
double valid = 0x1_0.8p1_0; // 16.5 × 2^10 = 16896.0

// SYNTAX ERROR: _ cannot be placed right after 0x, next to
// the dot, right after p, or right before the suffix:
// double a = 0x_1.8p0;
// double b = 0x1_.8p0;
// double c = 0x1.8p_2;
// float  d = 0x1.8p0_f;
```

For both uppercase and lowercase forms, the digits of the exponent part are still **decimal digits**. For example, `0x1p10` has exponent ten (multiply by `2^10`), **not** exponent 16 just because `10` looks like two hex digits.

## 7. Relationship with IEEE 754 and Exact Representability

A finite normal IEEE 754 `double` value has 1 sign bit, 11 exponent bits, and 52 fraction bits (64 bits total). For non-zero **normal** values, the effective significand is `1.<fraction bits>` in base 2 (the leading 1 bit is implicit). `float` has 32 bits total: 1 sign bit, 8 exponent bits, and 23 fraction bits.

This is why hex literals are convenient: a sequence of hex digits directly describes bit groups of the binary significand. For example, in `double`:

```java
double exact = 0x1.8p1;                  // 3.0, strictly exact
double oneTenth = 0x1.999999999999ap-4; // double value closest to 0.1
```

The value `oneTenth` has the common short decimal display `0.1`, yet **the stored binary value is not strictly equal to 1/10**. Here, hex literal syntax explicitly describes the rounded `double` number.

Do not assume "every hex literal is automatically strictly exact." If the significand provides more bits than `float`/`double` precision, or if the value falls exactly midway between two representable numbers, the compiler still applies the target type's rounding rules. Hex's advantage is a notation directly compatible with base 2, especially when writing **values already representable** in `double`/`float`.

Typical boundaries that can be written in hex:

```java
double maxFinite      = 0x1.fffffffffffffp1023; // Double.MAX_VALUE
double minNormal      = 0x1.0p-1022;           // Double.MIN_NORMAL
double minSubnormal   = 0x1p-1074;            // Double.MIN_VALUE

float maxFiniteFloat  = 0x1.fffffep127f;      // Float.MAX_VALUE
float minNormalFloat  = 0x1.0p-126f;          // Float.MIN_NORMAL
float minSubFloat     = 0x1p-149f;            // Float.MIN_VALUE
```

**Distinguish `MIN_VALUE` from the most negative number:** in `Double` and `Float`, `MIN_VALUE` is the **smallest non-zero positive finite value**, i.e., a *subnormal* number; it is not the negative value of largest magnitude. The finite negative number with the largest magnitude is `-Double.MAX_VALUE` or `-Float.MAX_VALUE`.

Finite literals also cannot increase the exponent indefinitely: non-zero literals whose rounding pushes them to infinity or to 0 are rejected by Java with a compile error. When you need `NaN` or infinity values, use constants such as `Double.NaN`, `Double.POSITIVE_INFINITY`, and `Float.NEGATIVE_INFINITY`; those are not hexadecimal floating-point literals.

## 8. `Double.toHexString`, `Float.toHexString`, and Parsing

Java has APIs to **output the hex form of a stored value**:

```java
Double.toHexString(3.0);        // "0x1.8p1"
Float.toHexString(3.0f);        // "0x1.8p1"
Double.toHexString(0.1);        // "0x1.999999999999ap-4"
Double.toHexString(-0.0);       // "-0x0.0p0"
```

Not every value prints in the exact form you typed. For instance, `0xA.Ap0` and `0x1.54p3` both represent `10.625`; `Double.toHexString(10.625)` returns the normalized form `"0x1.54p3"`.

- `Double.toHexString` and `Float.toHexString` return **character strings**, useful when comparing binary values.
- `Double.parseDouble`/`Double.valueOf` and `Float.parseFloat`/`Float.valueOf` can parse valid hex floating-point string forms, such as `"0x1.8p1"`.
- When inspecting raw bits, `Double.doubleToRawLongBits` and `Float.floatToRawIntBits` serve a different role: they return **the IEEE 754 encoded bits** as `long`/`int`. These raw bits include the sign bit, biased exponent, and fraction; they are not the hex literal string representation of the value.

Experiment:

```java
String representation = Double.toHexString(0.1);
double parsed = Double.parseDouble(representation);
System.out.println(representation);                   // 0x1.999999999999ap-4
System.out.println(parsed == 0.1);                    // true
```

The comparison above makes sense: after parsing the hex string, `parsed` and the decimal literal `0.1` produce the same **rounded `double` value**. It does **not** prove that `double` stores the mathematical fraction 1/10 with absolute exactness.

`NaN` and infinity cases output as special strings like `"NaN"` and `"Infinity"` (not `0x...p...`); the sign of `-0.0` is preserved in hex output.

## 9. Standalone Runnable Java 17+ Program

Create the file **`HexFloatLiteralDemo.java`**:

```java
public class HexFloatLiteralDemo {
    public static void main(String[] args) {
        double a = 0x1.8p1;
        double b = 0xA.Cp-2;
        float c = 0x1.Ap2f;

        int integerHex = 0x10;
        double floatingHex = 0x10p0;
        double normal = 0xA.Ap0;

        System.out.println("0x1.8p1 = " + a);
        System.out.println("0xA.Cp-2 = " + b);
        System.out.println("0x1.Ap2f = " + c);
        System.out.println("integer 0x10 = " + integerHex);
        System.out.println("floating 0x10p0 = " + floatingHex);
        System.out.println("toHexString(10.625) = "
                + Double.toHexString(normal));

        double decimal = 0.1;
        String exactHex = Double.toHexString(decimal);
        double parsed = Double.parseDouble(exactHex);

        System.out.println("decimal double 0.1 as hex = " + exactHex);
        System.out.println("parsed equals original = " + (parsed == decimal));
        System.out.println("negative zero as hex = "
                + Double.toHexString(-0.0));

        System.out.println("Double.MIN_VALUE as hex = "
                + Double.toHexString(Double.MIN_VALUE));
        System.out.println("Float.MIN_VALUE as hex = "
                + Float.toHexString(Float.MIN_VALUE));
    }
}
```

From the directory containing the file:

```bash
javac HexFloatLiteralDemo.java
java HexFloatLiteralDemo
```

**Expected output with Java 17+:**

```text
0x1.8p1 = 3.0
0xA.Cp-2 = 2.6875
0x1.Ap2f = 6.5
integer 0x10 = 16
floating 0x10p0 = 16.0
toHexString(10.625) = 0x1.54p3
decimal double 0.1 as hex = 0x1.999999999999ap-4
parsed equals original = true
negative zero as hex = -0x0.0p0
Double.MIN_VALUE as hex = 0x0.0000000000001p-1022
Float.MIN_VALUE as hex = 0x0.000002p-126
```

Analysis of results:

1. The first three literals represent `3`, `2.6875`, and `6.5` respectively; the `f` suffix on `c` selects type `float`.
2. `0x10` and `0x10p0` have the same magnitude, but different literal types.
3. `Double.toHexString(10.625)` puts the significand in normalized form `1.54 × 2^3`.
4. The string for `double 0.1` shows the nearest binary value, not the exact fraction 1/10.
5. `Double.MIN_VALUE` and `Float.MIN_VALUE` are **subnormal** numbers. The API's hex output uses a significand of the form `0.000...` and the minimum exponent for normal numbers, so it **differs in form** from short literals like `0x1p-1074` or `0x1p-149f` while having the same value. This formatting does not mean the constants above are wrong.

## 10. Step-by-Step Procedure to Read and Convert a Value to Hex Floating-Point

Suppose you need to represent the mathematical value `13.25` in a way that clearly describes it in base two.

**Step 1: Convert integer and fractional parts to binary.**

- `13 = 1101₂`.
- `0.25 = 0.01₂`.
- `13.25 = 1101.01₂`.

**Step 2: Group bits into fours to obtain hex digits.**

`1101.0100₂ = D.4₁₆`. Thus, the unnormalized representation is `0xD.4p0`.

**Step 3: Shift to a normalized-style significand `1.x × 2^E` (if desired).**

`1101.01₂ = 1.10101₂ × 2³`. Group the fraction into `1010 1000...₂`, which is `A8₁₆`. We get:

```text
13.25₁₀ = 1101.01₂
         = 0xD.4p0
         = 0x1.A8p3
         = (1 + 10/16 + 8/256) × 8
         = (1.65625) × 8
         = 13.25
```

`Double.toHexString(13.25)` returns `"0x1.a8p3"`. In normalized form, the exponent `3` indicates how many positions the binary point shifted, and does **not** depend on how many hex digits the significand has.

**Step 4: Choose type and suffix.** If an API requires `double`, `0x1.A8p3` suffices. If it requires `float`, write `0x1.A8p3f`. Because 13.25 has a finite and short binary representation, both represent it exactly.

## 11. Where to Use Hex Literals, and Where to Avoid Them

**Use them** when the problem involves bits, binary precision, or special constants:

- testing bit-level operations on `float`/`double` and comparing against expected IEEE 754 values;
- testing upper/lower boundaries between normal and subnormal numbers;
- reproducing a `double` value observed from `Double.toHexString`;
- expressing numbers easily written as powers of 2, such as `0x1p-10` (1/1024) or `0x1p20` (1,048,576).

**Prefer decimal literals** when the value carries base-10 business meaning, such as displayed weights, unit prices, and percentages in code/docs where readers expect decimal numbers. If the task requires **exact decimal monetary calculations and rounding rules**, use `BigDecimal` from strings (e.g., `new BigDecimal("0.1")`) instead of trying to solve it with hex-written `double`. Hex literals help express **a binary value of float/double** accurately; they do not turn IEEE 754 into infinite-precision decimal numbers.

**Readability:** named constants and comments explaining the choice help readers understand why `0x1.0p-1022` was written instead of a long decimal string. For ordinary numbers like 3.0, writing `3.0` is usually simpler than `0x1.8p1` when not studying bit representations.

## 12. Common Mistakes

| Mistake | Consequence / Fix |
| --- | --- |
| Thinking `p3` multiplies by `16^3` | It multiplies by `2^3` |
| Omitting `p` because `0x` is present | If the significand has a dot, a hex floating-point literal must have a `p` exponent |
| Using `e` as the hex exponent | In a hex significand, `e` is digit 14; must use `p` or `P` |
| Thinking `0x1e3` is the float `1×10³` | It is a base-16 integer literal with value 483 |
| Assigning `0x1p0` to `float` without suffix | Default literal is `double`; write `0x1p0f` |
| Placing `_` next to `0x`, `.`, `p`, `f` | Violates underscore rules; group only digits |
| Assuming hex literals never round | If too many bits or exceeding target precision, rounding still occurs |
| Assuming `0x1.999...p-4` is exact mathematical 1/10 | It is the binary `double` nearest to 0.1 |
| Mistaking `Double.MIN_VALUE` for the largest negative number | It is the smallest non-zero positive subnormal number |
| Confusing `Double.toHexString` with raw bits | The hex string is in `significand × 2^exponent` form, not 16 hex digits of all 64 bits |

## 13. Self-Check Exercises and Answers

**Exercise 1.** Calculate `0x1.Cp2` by hand.  
**Exercise 2.** Distinguish the value and literal type of `0x10`, `0x10p1`, and `0x10p1f`.  
**Exercise 3.** Express `0.375` as a hexadecimal floating-point literal.  
**Exercise 4.** Does `0x1ep1` have the value `1 × 10¹`? Compute the result.  
**Exercise 5.** `Double.toHexString(0.1)` returns `0x1.999999999999ap-4`. What does this prove, and what does it not prove?  
**Exercise 6.** Write a `float` literal for `5.5` and a `double` literal for `2^20`.

**Solutions:**

1. `C₁₆ = 12`, so `0x1.C = 1+12/16 = 1.75`; multiplying by `2²=4` gives `7.0`.
2. `0x10` is `int 16`; `0x10p1` is `double 32.0`; `0x10p1f` is `float 32.0f`.
3. `0.375 = 3/8 = 0.011₂ = 0x0.6p0`; can also be written as `0x1.8p-2`.
4. No. `e` is digit 14 so `0x1e = 30`; `p1` multiplies by 2, giving **60.0**.
5. It reveals the exact **stored binary value** for the `double` literal `0.1`. It does not prove that `double` stores the exact mathematical fraction `1/10`.
6. `5.5 = 0x1.6p2f` because `1.375 × 4 = 5.5`; `2^20 = 0x1p20` (type `double`).

**Remember:** **Hex** digits in the significand, **`p`** with a **base-2** exponent, **`f`/`F`** suffix to choose `float`, and **`double`** by default. This notation is especially powerful when you want to understand or reproduce binary floating-point values unambiguously.