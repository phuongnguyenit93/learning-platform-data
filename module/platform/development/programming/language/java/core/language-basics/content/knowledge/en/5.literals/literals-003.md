# Floating-Point Literals, Exponent Notation, and F or D Suffixes in Java 17+

A **floating-point literal** is a real number value written directly in Java code, such as `3.14`, `2e3`, or `0.5F`. It differs from an integer literal `2` in **type**, representation, and arithmetic behavior.

In Java 17, a floating-point literal **without a suffix** defaults to `double`. To explicitly mark a literal as `float`, add the suffix `F` or `f`; the suffix `D` or `d` confirms `double` type, though it is **optional**.

## 1. Recognizing the syntax

| Literal | Type | Mathematical value | Notes |
| --- | --- | --- | --- |
| `3.14` | `double` | 3.14 | No suffix |
| `3.14D` | `double` | 3.14 | `D` explicitly written |
| `3.14f` | `float` | 3.14 | `f`/`F` specifies float type |
| `2e3` | `double` | 2 × 10³ = 2000 | `e`/`E` is decimal exponent notation |
| `6.02E-3` | `double` | 6.02 × 10⁻³ | Negative exponent |
| `1.25e+2F` | `float` | 125 | Exponent with `+` sign, `F` suffix |
| `.5` | `double` | 0.5 | Digits before the dot may be omitted |
| `5.` | `double` | 5.0 | Digits after the dot may be omitted |
| `1_000.5` | `double` | 1000.5 | `_` groups digits in valid positions |
| `5` | `int` | 5 | **Integer** literal, not floating-point |

The symbol `e`/**`E`** here means "multiplied by `10` to an integer power," **not Euler's number**.

Typical structure:

~~~text
significand [e or E] [+ or - sign] exponent [F/f/D/d]
   1.25        e          -           3        F
~~~

For example, `1.25e-3F` is a `float` literal with mathematical value `0.00125`, rounded to `float` precision. If you use `e/E` notation, the exponent part must contain digits; `1e` and `1e+` are **invalid**.

Java also has hexadecimal floating-point literals such as `0x1.8p1` (equal to `3.0`, type `double`): `p/P` represents a **base-2** exponent, not `e/E`. This is a separate syntax and is not required to understand the decimal examples below.

## 2. Runnable Java 17 example

Create the file **`FloatingLiteralDemo.java`** (filename matching `public class`):

~~~java
public class FloatingLiteralDemo {
    public static void main(String[] args) {
        double regular = 12.5;
        double large = 1.25e3;
        double small = 6.02E-3;
        float withF = 2.5F;
        double withD = 2.5D;
        double leadingDot = .5;
        double trailingDot = 5.;
        double hex = 0x1.8p1;

        double fromIntegerDivision = 5 / 2;
        double fromFloatingDivision = 5 / 2.0;

        System.out.println("regular=" + regular);
        System.out.println("large=" + large);
        System.out.println("small=" + small);
        System.out.println("withF=" + withF);
        System.out.println("withD=" + withD);
        System.out.println("leadingDot=" + leadingDot);
        System.out.println("trailingDot=" + trailingDot);
        System.out.println("hex=" + hex);
        System.out.println("integerDivision=" + fromIntegerDivision);
        System.out.println("floatingDivision=" + fromFloatingDivision);
        System.out.println("exactEquality=" + (0.1 + 0.2 == 0.3));
    }
}
~~~

Open PowerShell (Windows) or a Bash terminal (Linux) in the directory containing the file, then run the **same commands**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 FloatingLiteralDemo.java
java FloatingLiteralDemo
~~~

**Expected output:**

~~~text
regular=12.5
large=1250.0
small=0.00602
withF=2.5
withD=2.5
leadingDot=0.5
trailingDot=5.0
hex=3.0
integerDivision=2.0
floatingDivision=2.5
exactEquality=false
~~~

**Why?** `1.25e3` equals `1250.0` even though printing does not necessarily preserve exponent form. `5 / 2` performs integer division between two `int`s, producing the integer `2` before converting to `double` `2.0`; conversely, `5 / 2.0` performs floating-point division, yielding `2.5`. The final comparison is `false` because certain decimal fractions (such as `0.1`) **cannot be represented exactly** in IEEE 754 binary floating-point.

## 3. `float` vs. `double`: suffix determines literal type

~~~java
double a = 1.5;  // Valid: default literal is double.
double b = 1.5D; // Valid: explicit D added.
float c = 1.5F;  // Valid: float literal.
double d = 1.5F; // Valid: float is widened to double.

// float e = 1.5; // Compile error: double does not automatically narrow to float.
~~~

| Criterion | `float` | `double` |
| --- | --- | --- |
| Size | 32 bits | 64 bits |
| Approximate precision | 6–7 significant decimal digits | 15–16 significant decimal digits |
| Literal suffix | `f` or `F` | `d`/`D`, or omit suffix |
| Examples | `0.1F` | `0.1`, `0.1D` |

Converting a `double` literal to `float` with a cast, such as `(float) 1.5`, can be valid, but **carries a risk of precision loss or range overflow**. When intentionally writing a `float` literal, using `F` is usually clearer.

A negative literal like `-2.5F` is parsed as the **negation** operator `-` applied to the literal `2.5F`; the minus sign is not an independent part of the literal token. This helps explain why expressions and literals can have separate rules.

## 4. Limits, underscore rules, and common mistakes

| Code or situation | Valid/invalid | Explanation |
| --- | --- | --- |
| `double rate = 1e-3;` | Valid | `0.001`, double type |
| `float rate = 1e-3F;` | Valid | `F` suffix, float type |
| `float rate = 1e-3;` | **Compile error** | Right-hand side is double; does not automatically narrow |
| `double n = 1e;` | **Compile error** | Missing exponent |
| `double n = 1_.0;` | **Compile error** | Underscore next to dot is invalid |
| `double n = 1_000.0;` | Valid | Valid digit grouping |
| `double n = 1e400;` | **Compile error** | Finite double literal exceeds representable range |
| `float n = 1e40F;` | **Compile error** | Finite float literal exceeds representable range |
| `double n = 5 / 2;` | Valid syntax, likely unintended | Result `2.0`, not `2.5` |

A **non-zero** floating-point literal so small that it rounds to 0 in the chosen type is also invalid when written directly; for example, `1e-400` underflows below the representable magnitude of `double`. However, **runtime operations** can still produce `Infinity`, `NaN`, *subnormal* numbers, or 0 due to underflow; that is a separate matter from compile-time literal checks.

### When should you avoid `float`/`double`?

These types represent **approximate** real numbers, suitable for scientific computing, graphics, and statistics where arithmetic rounding error is acceptable. For **money and calculations requiring exact decimal precision**, consider `BigDecimal` (initialized from a **string** when exact decimal values must be preserved), or integer currency units depending on the problem's requirements.

For example, `new java.math.BigDecimal("0.1")` preserves the exact decimal value `0.1` in the `BigDecimal` model, unlike `new BigDecimal(0.1)`, which receives an already approximated `double` value.

## 5. Self-check exercises

1. **Identify the type:** `7.5`, `7.5f`, `2e2`, `2e2D`.  
   *Answer:* `double`, `float`, `double`, `double`, respectively.
2. **Convert to standard decimal:** `3.2e2` and `6.5E-2F`.  
   *Answer:* Mathematical values `320` and `0.065`, respectively; the second literal has type `float`.
3. **Fix the error:** `float x = 0.25;`.  
   *Answer:* `float x = 0.25F;`, or choose `double x = 0.25;`.
4. **Predict:** `double x = 7 / 2;` and `double y = 7 / 2.0;`.  
   *Answer:* `x == 3.0`, `y == 3.5`.
5. **Test precision:** run `System.out.println(0.1 + 0.2 == 0.3);`.  
   *Answer:* `false`; do not mechanically use `==` to compare approximate floating-point calculation results.

**Key takeaway:** In Java 17, floating-point literals default to `double`; the `F/f` suffix changes the type to `float`, while `D/d` merely makes `double` explicit. The `e/E` notation multiplies by a power of 10; the type of the **operands right at the operation** determines division behavior and precision, not just the variable type on the left-hand side.
