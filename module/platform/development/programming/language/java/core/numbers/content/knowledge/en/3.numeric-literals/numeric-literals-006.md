# Floating-Point Literals, Exponent Notation, and F, D Suffixes in Java

## 1. Lesson Objectives

In Java, a **floating-point literal** is a way of writing a real numeric value directly in source code. This lesson belongs to the **Literals and Bases** section of Java Core — Numbers. After studying it, you should be able to:

- Read and write decimal literal forms correctly, such as `3.14`, `.5`, `10.`, `6.02e23`.
- Understand that `e`/`E` exponent notation represents a **power of 10**, while `p`/`P` in hexadecimal literals represents a **power of 2**.
- Know that `f`/`F` produces a `float` literal; `d`/`D` or no suffix produces a `double` literal.
- Distinguish **literal type**, **receiving variable type**, **casting**, and **storage precision**.
- Identify rules for signs, decimal points, digits, underscores, syntax errors, and out-of-range literals.
- Cross-check the Java Language Specification (JLS) yourself and run the examples with JDK 17 or higher.

**Key point:** a literal is parsed and assigned its type at compile time. Floating-point numbers in Java programs use a period `.`, not a comma `,` as used for numbers in some natural languages.

## 2. What Is a Floating-Point Literal?

Let us start with these declarations:

```java
int whole = 12;
double fraction = 12.0;
double scientific = 1.2e1;
float small = 12.0F;
```

All four variables can represent the quantity twelve, yet their **types and source syntax are not the same**:

| Notation | Token/Type Kind | Meaning |
| --- | --- | --- |
| `12` | Integer literal of type `int` | Twelve |
| `12L` | Integer literal of type `long` | Twelve, still an integer |
| `12.0` | Floating-point literal of type `double` | Twelve as floating point |
| `12.` | Floating-point literal of type `double` | Equivalent to `12.0` |
| `.5` | Floating-point literal of type `double` | One half |
| `12e0` | Floating-point literal of type `double` | 12 × 10⁰ |
| `12f`, `12.0F` | Floating-point literal of type `float` | Twelve as `float` |
| `12d`, `12.0D` | Floating-point literal of type `double` | `D` suffix states the default type explicitly |
| `0x1.8p3` | Floating-point literal of type `double`, hex form | (1 + 8/16) × 2³ = 12 |

In Java, primitive floating-point numbers consist of two types:

- `float`: IEEE 754 **binary32** format, with roughly 24 significand bits (approximately 6–9 significant decimal digits when representing/round-tripping).
- `double`: IEEE 754 **binary64** format, with roughly 53 significand bits (approximately 15–17 significant decimal digits when representing/round-tripping).

That is **finite binary precision**, not a count of digits after the decimal point. Do not conclude that a literal with many decimal digits will be preserved exactly in `double` or `float`.

## 3. Four Syntactic Forms of Decimal Floating-Point Literals

According to JLS `3.10.2, a decimal literal must have **at least one digit**, and must have **a decimal point, an exponent part, or a floating-point type suffix**. Below are the four typical forms:

| Form | Valid Examples | Explanation |
| --- | --- | --- |
| Digits then decimal point, with or without fractional digits | `1.`, `1.25`, `1.25e2` | Presence of `.` makes it a floating-point literal |
| Decimal point then digits | `.25`, `.25F`, `.25e+2` | Omitting the 0 before the decimal point is allowed |
| Digits then exponent part | `1e3`, `12E-2`, `10e0D` | `e`/`E` suffices to make it a floating-point literal |
| Digits then `F/f/D/d` suffix | `1f`, `20F`, `3d` | Suffix identifies the type even without `.` |

Specifically, all of the following literals are valid:

```java
double a = 7.0;
double b = 7.;
double c = .7;
double d = 7e2;
double e = 7.0E-2;
float f = 7f;
float g = .7F;
double h = 7D;
```

Conversely, `7` is an `int` integer literal; assigning it to a `double` variable is a **widening conversion**, and does not turn the token `7` into a floating-point literal. This is an important distinction when analyzing overloads, expressions, and intermediate values.

**Do not use commas in literals:** `3,14` does not create the floating-point number "three point one four." In Java syntax, a comma acts as a separator in certain constructs. Write `3.14` in source code; use locale formatting only when handling input/output strings.

## 4. Decimal Exponent Notation: e and E

Easy-to-remember general form:

```text
significand e or E optional_exponent_sign exponent_digits
```

Mathematically, `aeb` means **a × 10ᵇ** where `a` and `b` are the significand and exponent respectively. The letter `e` is a syntactic marker, **not** Euler's constant `e ≈ 2.71828...`.

| Literal | Mathematical Calculation | Value |
| --- | --- | --- |
| `1e3` | 1 × 10³ | 1000 |
| `2.5E2` | 2.5 × 10² | 250 |
| `6.25e-2` | 6.25 × 10⁻² | 0.0625 |
| `1E+2` | 1 × 10² | 100 |
| `7e0` | 7 × 10⁰ | 7 |
| `.75e+1` | 0.75 × 10¹ | 7.5 |

- `e` and `E` are equivalent; `1e3` and `1E3` have the same `double` type and the same value.
- After `e`/`E`, **an integer exponent written with decimal digits is required**.
- A `+`/`-` sign immediately after `e`/`E` is a valid part of the exponent: `1e+3`, `1e-3`.
- `1e`, `1e+`, and `1e-` lack a complete exponent and are invalid.
- `1e2.5` is invalid as a literal; the exponent must be an integer.
- Exponent notation does not convert a literal to `BigDecimal`; `6.02e23` is still a `double` if it has no `F` suffix.

**Note when reading logs:** Java may print `1.0E7` instead of an all-digit string. How `Double.toString`/`Float.toString` chooses a string representation is a matter of **value output**, separate from source literal syntax `1e7`.

## 5. Suffixes F/f and D/d Determine the Literal's Type

Standard language rule:

| Suffix | Literal Type | Examples |
| --- | --- | --- |
| `f` or `F` | `float` | `3.14f`, `5F`, `2e-3F` |
| `d` or `D` | `double` | `3.14d`, `5D`, `2e-3D` |
| No suffix | `double` | `3.14`, `5e0`, `0x1p1` |

Suffixes can be uppercase or lowercase. Prefer `F` and `D` when clarity about type is needed; `D` can usually be omitted since `double` is already the default.

### 5.1. Literal Type vs. Receiving Variable Type

```java
float a = 1.25F;       // float -> float
double b = 1.25;       // double -> double
double c = 1.25F;      // float -> double, widening
double d = 1.25D;      // double -> double
double e = 1;          // int -> double, widening
```

In `double c = 1.25F;`, **the value is created at `float` precision first**, and only then widened to `double`. Widening does not recover digits already lost in `float`.

The following example **does not compile**:

```java
float wrong = 1.25;
```

Because `1.25` has no suffix, it is a `double` literal; Java does not automatically narrow from `double` to `float` in such an assignment. Fix it to `float correct = 1.25F;`. You can use an explicit cast `(float) 1.25` when appropriate, but you should not replace the suffix merely to silence a narrowing warning.

Similar case:

```java
float rate = 1e2F;  // valid, float
double distance = 1e2; // valid, double
// float bad = 1e2;    // compile error: double -> float
```

### 5.2. Why Are 0.1F and 0.1 Not "Identical"?

`0.1F` is rounded to binary32 representation; `0.1` is rounded to binary64. When a `float` is widened to `double` for comparison or assignment, the value already rounded in binary32 keeps that rounded value. Thus, **literals with different suffixes can produce different values**, even when they have the exact same decimal digits in source code.

Only use `D` when it helps readers or a code generator see the intent clearly. Do not choose `F` just to save memory without evaluating the rounding error for your problem.

### 5.3. F/D Are Not Type-Conversion Operators or Units

`1.5F` is **a `float` literal**; `(float) 1.5` is **a cast** on a `double` literal. `L` denotes an integer `long` literal and cannot be attached to floating-point numbers: `1.5L` or `1e3L` is invalid. Java also has no built-in suffix like `M` to create a `BigDecimal` as some other languages do.

## 6. Hexadecimal Floating-Point Literals and p/P Notation

In addition to decimal floating-point numbers, Java allows **hexadecimal floating-point literals**. This form starts with `0x` or `0X`, uses hexadecimal digits `0–9` and `A–F/a–f` for the **significand**, and **requires a `p`/`P` exponent part**.

Key difference:

- `1.5e2` = 1.5 × **10²** = 150.
- `0x1.8p2` = (1 + 8/16) × **2²** = 6.
- `0x1.fp2` = (1 + 15/16) × **2²** = 7.75.

Even though the significand's digits are **base 16**, the `p` exponent is a **power of 2**. The digits written after `p`/`P` are **decimal** digits of the exponent, not hexadecimal.

| Hex Literal | Interpretation | Decimal Value |
| --- | --- | --- |
| `0x1p0` | 1 × 2⁰ | 1 |
| `0x1p3` | 1 × 2³ | 8 |
| `0x1.8p1` | (1 + 8/16) × 2¹ | 3 |
| `0x1.fp2` | (1 + 15/16) × 2² | 7.75 |
| `0x.8p0` | (8/16) × 2⁰ | 0.5 |
| `0x1p-3F` | 1 × 2⁻³, type `float` | 0.125 |
| `0X1.0P+2D` | 1 × 2², type `double` | 4 |

You may write `0x1.p3` or `0x1p3` (a decimal point after `0x1` is optional), as long as there are significand digits and a `p`/`P` with a valid exponent.

**Why use hex?** Binary-aligned values like `0x1.8p1` can describe exact bits and powers of 2, which is handy when reading IEEE 754 specs, inspecting bits, or needing an exact binary value. For instance, `0x1.0p-3` represents `0.125` exactly in binary32/binary64. Use decimal floating-point numbers when base-10 business semantics are easier to read.

**Distinguishing from hex integers:** `0x10` is an `int` integer literal equal to 16; `0x10p0` is a `double` floating-point literal equal to 16. `0x1.8` is invalid as a floating-point literal because it lacks `p` and an exponent.

## 7. Minus Signs, Plus Signs, and Underscores

### 7.1. Signs Before the Number vs. Signs in the Exponent

In `-1.25F`, the `-` before the literal is the **unary minus operator** acting on the positive literal `1.25F`; the floating-point literal token itself does not include a leading minus sign. In contrast, the `-` in `1e-3` or `0x1p-3` **is part of the exponent** of the literal.

Example:

```java
double negative = -1.5;
double thousandth = 1e-3;
double tinyPowerTwo = 0x1p-3;
double positive = +.5;
```

These variables have the values `-1.5`, `0.001`, `0.125`, and `0.5`, respectively. Do not put a `-` sign after a suffix: `1.5F-` does not create a negative literal.

### 7.2. Underscores Between Digits

`_` allows grouping digits in the **integer part, fractional part, and exponent part** without changing the numeric value:

```java
double a = 1_234.5_6;
double b = 1.2_5e+1_0;
float c = 0x1.8_0p+1F;
```

These forms are valid. `_` must be **between digits of the same component**. The following notations are invalid:

```java
// double a = _1.0;    // underscore at the start
// double b = 1_.0;    // immediately before decimal point
// double c = 1._0;    // immediately after decimal point
// double d = 1e_3;    // immediately after e
// double e = 1e+_3;   // immediately after exponent sign
// float  f = 1.0_F;   // immediately before suffix
// double g = 0x_1p0;  // immediately after 0x prefix
```

A literal may contain multiple consecutive `_` **if they lie between digits**; although valid, prefer clear, readable grouping.

## 8. Precision and Literal Compilation

When `javac` encounters a valid literal, it converts the source digits into a representable value of type `float` or `double` according to Java's rules. Two source representations that appear to express the same mathematical quantity do not guarantee all digits are preserved identically in binary32/binary64.

### 8.1. 0.1 Is the Classic Case

`0.1` in decimal cannot be represented exactly as a finite binary fraction. Therefore:

- `double d = 0.1;` creates a binary64 value close to `0.1`.
- `float f = 0.1F;` creates a binary32 value close to `0.1`.
- `double widened = f;` widens **that already rounded binary32 value**; it does not make it equal to the binary64 value of the `0.1` literal.

Notably, `System.out.println(0.1F)` can still print `0.1`: the floating-point-to-string conversion algorithm chooses a short decimal form that round-trips back to that value; it **does not prove** the stored value equals exactly 1/10.

### 8.2. Hex Can Represent Binary Fractions Exactly

`0x1p-1` equals exactly `0.5` and `0x1p-3` equals exactly `0.125`. Values that are multiples/powers of 2 fitting within the exponent and precision bounds can be represented exactly in IEEE 754 binary format.

Do not conclude that every hex literal suffers no precision loss. If the significand has too many bits or the exponent pushes the value outside the representable range, rounding or a compile error still occurs.

### 8.3. Use BigDecimal When Exact Decimal Representation Is Required

If business logic requires exact decimal numbers like `0.1`, you can construct:

```java
java.math.BigDecimal price = new java.math.BigDecimal("0.1");
```

This is a **constructor call from a `String`**, not a BigDecimal literal. Using `new BigDecimal(0.1)` passes the approximate binary `double` value into the object, so it cannot replace constructing from a string when an exact decimal `0.1` is required.

## 9. Boundaries: Overflow, Underflow, and Special Values

### 9.1. Literals That Are Too Large or Too Small

Java distinguishes between **out-of-range floating-point literals** and **runtime operations producing special values**.

- A **non-zero** literal so large that rounding converts it to infinity causes a **compile error**.
- A **non-zero** literal so small that rounding converts it to `0.0` also causes a **compile error**.
- If the small result is still a **non-zero subnormal**, the literal can still be valid.

The following examples intentionally **do not compile**:

```java
// double tooLarge = 1e400;   // overflows to Infinity when converting literal
// float tooLargeF = 1e40F;   // overflows float range
// double tooTiny = 1e-400;   // non-zero literal rounded to zero
// float tooTinyF = 1e-50F;   // same for float
```

These comments illustrate errors if `//` is removed; do not uncomment them and mix them with runnable examples.

Reference limits: `Float.MAX_VALUE` is the largest positive finite `float`; `Double.MAX_VALUE` is the largest positive finite `double`. `Float.MIN_VALUE` and `Double.MIN_VALUE` are the **smallest non-zero positive (subnormal)** values of each type, **not the most negative number**. `MIN_NORMAL` is the smallest positive normal value.

For example, `1.4e-45F` is a decimal form that rounds to `Float.MIN_VALUE`, while `0x1p-149F` represents that exact smallest value. For `double`, `0x1p-1074` is the value of `Double.MIN_VALUE`.

### 9.2. NaN and Infinity Are Not Keyword Literals

Java does **not** have floating-point literal syntax named `NaN` or `Infinity`. Use:

```java
double positiveInfinity = Double.POSITIVE_INFINITY;
double negativeInfinity = Double.NEGATIVE_INFINITY;
double notANumber = Double.NaN;

boolean ok = Double.isNaN(notANumber);
```

Runtime operations like `1.0 / 0.0` can yield `Infinity` and `0.0 / 0.0` can yield `NaN` under floating-point arithmetic. Unlike `int` division by 0, floating-point division by 0 does not throw `ArithmeticException` by default.

### 9.3. Sign of Zero

`0.0` and `-0.0` compare `true` with `==`, yet IEEE 754 has two distinct bit patterns. For example, `1.0 / 0.0` yields positive infinity, while `1.0 / -0.0` yields negative infinity. This is why `-0.0` should not be treated as completely equivalent to `0.0` in all floating-point computations.

## 10. Complete Example: Reading Literals, Exponents, and Suffixes

Save the entire content as **`FloatingLiterals.java`**:

```java
public class FloatingLiterals {
    public static void main(String[] args) {
        double decimal = 12.5;
        double leadingDot = .75;
        double scientific = 1.2e3;
        float asFloat = 1.25F;
        double hexadecimal = 0x1.8p1;
        float binaryExponent = 0x1p-3F;

        System.out.println(decimal);
        System.out.println(leadingDot);
        System.out.println(scientific);
        System.out.println(asFloat);
        System.out.println(hexadecimal);
        System.out.println(binaryExponent);
        System.out.println(Double.toHexString(hexadecimal));
        System.out.println(0.1F == 0.1);
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac --release 17 FloatingLiterals.java
java FloatingLiterals
```

**Exact stdout:**

```text
12.5
0.75
1200.0
1.25
3.0
0.125
0x1.8p1
false
```

Explanation:

1. `12.5` and `.75` use decimal syntax; `1.2e3` = 1200.0.
2. `1.25F` has type `float` and is printed by `println` as `1.25`.
3. `0x1.8p1` = (1 + 8/16) × 2 = `3.0`; `0x1p-3F` = 1/8 = `0.125`.
4. `Double.toHexString` produces the hex representation string of a `double` value; for `3.0`, the result is `0x1.8p1`.
5. `0.1F == 0.1` is `false` because the `float` operand is converted to `double` for comparison while still carrying the binary32 rounding error; the two operands do not hold the same value.

## 11. Complete Example: Precision, Zero, and Special Values

Save as **`LiteralPrecision.java`**:

```java
public class LiteralPrecision {
    public static void main(String[] args) {
        double decimal = 0.1;
        float single = 0.1F;
        double widened = single;

        System.out.println(decimal == widened);
        System.out.println(widened);
        System.out.println(0x1.0p-1 == 0.5);
        System.out.println(Double.doubleToRawLongBits(-0.0)
                == Double.doubleToRawLongBits(0.0));
        System.out.println(Double.isInfinite(1.0 / 0.0));
    }
}
```

Run:

```bash
javac --release 17 LiteralPrecision.java
java LiteralPrecision
```

**Exact stdout:**

```text
false
0.10000000149011612
true
false
true
```

Interpretation: converting `0.1F` to `double` clearly displays the approximate binary32 value; `0x1.0p-1` and `0.5` both equal exactly 1/2; positive and negative zero have different bit patterns; dividing a positive `double` by 0.0 yields infinity, so `Double.isInfinite` returns `true`.

## 12. Invalid Examples to Recognize When Reading Code

The following lines are **intentionally invalid code** for recognizing errors, not a standalone compilable Java snippet:

```java
// double a = 1e;         // exponent missing digits
// double b = 1e+;        // exponent missing digits after sign
// double c = 1e2.5;      // exponent is not an integer
// double d = 0x1.8;      // hex float requires p/P
// double e = 0x1.8e2;    // e is a hex digit, does not substitute for exponent p
// float  f = 1.25;       // double literal does not auto-assign to float
// double g = 1.5L;       // L is only for integer literals
// double h = 1e3L;       // cannot attach L after floating-point number
// double i = 1.0_M;      // misplaced underscore, M is not a float/double suffix
// double j = 1e400;      // non-zero literal overflows to Infinity
// float  k = 1e-50F;     // non-zero literal underflows to zero
```

Another code-reading mistake: thinking `2e3F` means 2 × 10³ and then "converted to float at the end." In reality, **the entire token `2e3F`** is a `float` literal, and its value already obeys binary32 rounding rules when created.

## 13. Quick Decision Table

| Want to Represent | Write | Avoid Confusing |
| --- | --- | --- |
| Decimal `double` number | `2.5` or `2.5D` | `2.5` is already `double` by default |
| Decimal `float` number | `2.5F` | `float x = 2.5;` is invalid |
| Power of 10 | `2.5e3` | `e` is not Euler's constant |
| Power of 10 for `float` | `2.5e3F` | Exponent does not alter type rules |
| Binary-exact representation in hex | `0x1.4p2` | Hex exponent uses `p`, meaning 2² |
| Hex floating-point of type `float` | `0x1p-3F` | Unsuffixed `0x1p-3` is `double` |
| Base-16 integer | `0x10` | This is an `int`, not a hex float |
| Exact decimal currency value | `new BigDecimal("2.50")` | Java has no `BigDecimal` literal |
| Infinity / NaN | `Double.POSITIVE_INFINITY`, `Double.NaN` | `Infinity`/`NaN` are not literal tokens |

## 14. Practice Exercises and Explained Answers

**Exercise 1 — Identify types.** Given `3`, `3F`, `3D`, `3.0`, `3e0`, `0x3p0`, and `0x3`, classify them into `int`/`float`/`double` before checking the answer.

Answer: `3` and `0x3` are `int`; `3F` is `float`; `3D`, `3.0`, `3e0`, and `0x3p0` are `double`.

**Exercise 2 — Compute exponent values.** Compute by hand: `1.5e2`, `1.5e-2`, `0x1.8p2`, and `0x1p-4`.

Answers in order: `150.0`, `0.015`, `6.0`, and `0.0625`. The first two multiply by powers of 10; the last two multiply by powers of 2.

**Exercise 3 — Find the errors.** Where are the errors in `float x = 2.5;`, `double y = 1e;`, and `double z = 0x1.8;`?

Answer: `2.5` defaults to `double` and cannot automatically narrow to `float`; `1e` is missing an exponent; hex float `0x1.8` is missing the `p` exponent. Corresponding fixes: `2.5F`, `1e0`, and `0x1.8p0`.

**Exercise 4 — Distinguish precision.** Explain why `double d = 0.1F;` and `double e = 0.1;` can differ even though both variables have type `double`.

Answer: the **literal's** type determines the first rounding step. `0.1F` is rounded in binary32 before widening; `0.1` is rounded directly in binary64.

**Exercise 5 — Read signs.** In `-0x1p-3F`, how many minus signs are there and what is each one's role?

Answer: two signs. The first is the unary minus operator acting on the literal; the sign after `p` is the sign of the exponent `-3`. The result is `-0.125F`.

**Exercise 6 — Distinguish compile-time vs. runtime errors.** Why is `double x = 1e400;` a compile error while `double x = 1.0 / 0.0;` can produce infinity at runtime?

Answer: a **non-zero literal** that rounds to infinity is a compile error per the JLS, whereas floating-point division has rules for producing special IEEE 754 values.

## 15. Mastery Checklist

- [ ] I can distinguish `1`, `1.0`, `1e0`, `1F`, and `1D` by literal kind.
- [ ] I can explain that `e/E` multiplies by a power of 10, while `p/P` multiplies by a power of 2.
- [ ] I can convert `0x1.8p1` to `3.0` on my own and understand why hex floats always require an exponent part.
- [ ] I know unsuffixed literals are `double`; `F/f` is `float`; `D/d` confirms `double`.
- [ ] I can explain why `float x = 1.2;` fails even though the value looks small.
- [ ] I can place underscores properly and distinguish unary minus from an exponent's minus sign.
- [ ] I do not confuse how `0.1F` is displayed with its storage precision.
- [ ] I know overly large/small literals can cause **compile** errors, while `NaN`/`Infinity` are constants/APIs or operation results.
- [ ] I ran both complete examples and verified stdout myself.

**Standard reference documentation:** [Java Language Specification 17, `3.10.2 Floating-Point Literals](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.2); [JLS 17, `4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3); [Java SE 17, Float API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html); [Java SE 17, Double API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html).