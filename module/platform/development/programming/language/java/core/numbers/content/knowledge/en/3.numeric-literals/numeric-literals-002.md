# The `L` Suffix for `long` and When Integer Literals Go Out of Range in Java

When writing `long value = 3_000_000_000;`, many people assume the compiler will look at the `long` variable type and automatically accept this number. In reality, Java **determines the literal's type before evaluating the assignment**. For decimal integer literals without the `L` suffix, the value must normally fit within the `int` range. Because `3_000_000_000` is larger than `Integer.MAX_VALUE`, the code above does not compile. The correct way is:

```java
long value = 3_000_000_000L; // long literal, value 3 billion.
```

This lesson distinguishes three easily confused phenomena: **a literal that is invalid at compile time**, **an `int` expression result that overflows before being converted to `long`**, and **`long` arithmetic that can still overflow at runtime**.

## 1. What Is an Integer Literal? What Does the `L` Suffix Change?

An integer literal is a whole number written directly in source code, such as `42`, `3_000_000_000L`, `0xFF`, or `0b1010`. Java has four ways to write integer numbers: decimal, hexadecimal (`0x`/`0X`), binary (`0b`/`0B`), and octal (typically starting with `0`, such as `017`).

**The `L` or `l` suffix gives the literal type `long`**. You should use uppercase `L`, because lowercase `l` is easily confused with the digit `1`. Without a suffix, an integer literal has type `int` if it is valid according to the range rules and the negative-boundary exception explained below.

| Written in Java | Literal Type | Meaning |
| --- | --- | --- |
| `42` | `int` | Integer 42 |
| `42L` | `long` | Integer 42 as a 64-bit type |
| `2_147_483_647` | `int` | Maximum positive value of `int` |
| `2_147_483_648L` | `long` | Exceeds `int`, still within `long` range |
| `0xFFL` | `long` | Value 255 written in base 16 |
| `0b1010L` | `long` | Value 10 written in base 2 |
| `017L` | `long` | Value 15 written in base 8 |
| `1.0` | `double` | Floating-point literal, not an integer literal |

Underscores `_` inside a literal help group digits for readability but **do not affect the value or type**: `3_000_000_000L` is equivalent to `3000000000L`. Do not place `_` before/after the digit sequence, immediately after the `0x`/`0b` prefix, or between a digit and `L`: `3_000L` is valid, while `3_000_L` is not.

## 2. `int` and `long` Ranges and How Java Accepts Decimal Literals

| Type | Width | Minimum | Maximum |
| --- | ---: | ---: | ---: |
| `int` | 32-bit signed | `-2_147_483_648` | `2_147_483_647` |
| `long` | 64-bit signed | `-9_223_372_036_854_775_808L` | `9_223_372_036_854_775_807L` |

For **decimal** integers:

- A literal without the `L` suffix has a normal positive limit of `2_147_483_647` (`Integer.MAX_VALUE`). For example, `2_147_483_648` standing alone is invalid.
- A literal with the `L` suffix has a normal positive limit of `9_223_372_036_854_775_807L` (`Long.MAX_VALUE`). `9_223_372_036_854_775_808L` standing alone is invalid.
- There is a **special exception for the two negative boundary values**: Java allows the decimal digits `2147483648` without `L` **only when it is the operand of the unary minus operator** in `-2147483648`, to represent `Integer.MIN_VALUE`. Similarly, `-9223372036854775808L` represents `Long.MIN_VALUE`. This is not an automatic type-conversion mechanism when a positive literal exceeds the limit.

The `-` sign is the **unary minus operator** acting on the literal, not part of the literal's syntax. Therefore, boundary cases require examining both the expression and its context, rather than merely counting digits.

```java
int maxInt = 2_147_483_647;
int minInt = -2_147_483_648;             // Negative-boundary exception: valid.
long aboveInt = 2_147_483_648L;          // Must use L.
long maxLong = 9_223_372_036_854_775_807L;
long minLong = -9_223_372_036_854_775_808L; // Negative boundary of long: valid.
```

The snippet above consists of valid declarations that can be placed inside a Java method. **You cannot increase the limit of `long` simply by adding `L`**: a value larger than `Long.MAX_VALUE` still does not become a valid `long`.

## 3. Why a `long` Variable Cannot Rescue an Oversized `int` Literal

Consider the invalid code below (only to illustrate the error; do not include it in a runnable program):

```java
long total = 3_000_000_000; // COMPILE ERROR: integer literal too large for int.
```

The compiler processes **the type and validity of the literal in the expression first**, and only then checks whether the result can be assigned to the variable. A target type of `long` allows a *widening primitive conversion* from an **already valid** `int` value, but it does not change how an out-of-range `int` literal is parsed.

```java
long small = 123;             // Valid: int 123 widens to long.
long large = 3_000_000_000L;  // Valid: the literal itself is already long.
```

There is no rule that "a decimal literal without `L` automatically becomes `long` if it is larger than `int`." When a directly written number exceeds `int`, declare the literal as `long` right away.

All the examples below **fail to compile**, but for different reasons:

```java
long a = 2_147_483_648;           // Decimal int literal out of range.
long b = 9_223_372_036_854_775_808L; // Decimal long literal out of range.
int c = 3_000_000_000L;          // Valid long literal, but cannot be directly assigned to int.
```

On line `c`, the error is a lossy assignment from `long` to `int`; the `L` suffix resolves **the literal's type**, it does not grant permission for automatic narrowing conversion.

## 4. Special Notes for Binary, Octal, and Hexadecimal Literals

**Non-decimal** literals also follow bit-pattern rules. For instance, `0xFFFF_FFFF` is valid without `L`: all 32 bits are 1 and are interpreted as the signed `int` value **-1**. Meanwhile, `0xFFFF_FFFFL` uses 64-bit `long`, with the low 32 bits set to 1, so its value is **4_294_967_295**.

```java
int minViaBits = 0x8000_0000;    // -2147483648 (sign bit of int is set).
int minusOne = 0xFFFF_FFFF;      // -1 (all 32 bits are set).
long positive = 0xFFFF_FFFFL;    // 4294967295 (is a 64-bit long).
long minLongBits = 0x8000_0000_0000_0000L; // Long.MIN_VALUE.
long allLongBits = 0xFFFF_FFFF_FFFF_FFFFL;  // -1L.
```

This is valid code that can be placed inside a Java method. With non-decimal literals, **the exact same digit sequence** can carry different signed numeric meanings depending on whether the type is 32-bit `int` or 64-bit `long`. Patterns exceeding 32 bits without `L` are still errors, such as `0x1_0000_0000`; adding `L` to a pattern that fits in 64 bits makes it valid.

Do not infer from `0xFFFF_FFFF` being accepted that `4_294_967_295` is also a valid `int`. The two notations use different validation rules: decimal numbers express magnitude, whereas binary/octal/hexadecimal literals can express signed bit patterns.

## 5. Two Kinds of Overflow to Distinguish: Out-of-Range Literal vs. Operation Overflow

**A. Out of range when writing the literal: compile error.** For example, `long n = 3_000_000_000;` fails before running. Adding the `L` suffix gives the number type `long`, making it usable.

**B. Individual literals are valid, but the operation overflows: compiles and runs with an incorrect result.** Example:

```java
long wrong = 2_000_000_000 + 1_000_000_000;   // -1294967296
long right = 2_000_000_000L + 1_000_000_000; // 3000000000
```

On the first line, both operands are `int`; the addition is performed in `int`, the result exceeds `Integer.MAX_VALUE`, and so it overflows to `-1_294_967_296`. Java only converts the **already overflowed result** to `long` during assignment. On the second line, one operand has type `long`, the other operand is promoted to `long`, and the addition is computed within the 64-bit range.

**Adding `L` or casting must happen before an operation at risk of overflow.** Casting after the calculation cannot recover lost bits:

```java
long wrongProduct = 100_000 * 100_000;          // int overflow -> 1410065408L
long alsoWrong = (long) (100_000 * 100_000);    // Casting after overflow has already occurred.
long rightProduct = 100_000L * 100_000;         // 10000000000L
long alsoRight = ((long) 100_000) * 100_000;     // Casting before multiplication.
```

In common binary arithmetic operations, if at least one operand is `long` (and neither is `float`/`double`), the operation's result is computed as `long`. However, **`long` also has limits**: `Long.MAX_VALUE + 1L` wraps around to `Long.MIN_VALUE`. Standard integer `+`, `-`, and `*` operations do not automatically throw exceptions on overflow.

Note that an `int` constant expression can also overflow when evaluated at compile time. For example, `int wrapped = Integer.MAX_VALUE + 1;` has the value `Integer.MIN_VALUE`. "Evaluated ahead of time by the compiler" does not mean "the compiler will catch arithmetic overflow errors." Division by 0 is a separate situation from addition/multiplication overflow.

## 6. Standalone Runnable Program (Java 17 or Higher)

Save with the exact filename **`LongLiteralDemo.java`**:

```java
public class LongLiteralDemo {
    public static void main(String[] args) {
        long largeLiteral = 3_000_000_000L;
        int intMin = -2_147_483_648;
        long longMin = -9_223_372_036_854_775_808L;

        long tooLate = 2_000_000_000 + 1_000_000_000;
        long promotedEarly = 2_000_000_000L + 1_000_000_000;
        long productTooLate = 100_000 * 100_000;
        long productCorrect = 100_000L * 100_000;

        int allIntBits = 0xFFFF_FFFF;
        long sameHexDigitsWithL = 0xFFFF_FFFFL;

        System.out.println("largeLiteral=" + largeLiteral);
        System.out.println("intMin=" + intMin);
        System.out.println("longMin=" + longMin);
        System.out.println("tooLate=" + tooLate);
        System.out.println("promotedEarly=" + promotedEarly);
        System.out.println("productTooLate=" + productTooLate);
        System.out.println("productCorrect=" + productCorrect);
        System.out.println("allIntBits=" + allIntBits);
        System.out.println("sameHexDigitsWithL=" + sameHexDigitsWithL);
        System.out.println("parsed=" + Long.parseLong("3000000000"));
        System.out.println("longOverflow=" + (Long.MAX_VALUE + 1L));

        try {
            Math.multiplyExact(100_000, 100_000);
        } catch (ArithmeticException ex) {
            System.out.println("multiplyExact=overflow detected");
        }
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 LongLiteralDemo.java
java LongLiteralDemo
```

Exact stdout output:

```text
largeLiteral=3000000000
intMin=-2147483648
longMin=-9223372036854775808
tooLate=-1294967296
promotedEarly=3000000000
productTooLate=1410065408
productCorrect=10000000000
allIntBits=-1
sameHexDigitsWithL=4294967295
parsed=3000000000
longOverflow=-9223372036854775808
multiplyExact=overflow detected
```

The program demonstrates three things: a 3-billion decimal literal requires `L`; addition/multiplication performed in `int` can overflow before the result is assigned to `long`; and with the same 8 hex digits `FFFFFFFF`, adding `L` changes the bit interpretation from 32-bit width to 64-bit width. `Math.multiplyExact` illustrates another option: asking Java to **throw `ArithmeticException`** when integer multiplication overflows.

## 7. Want to Detect Overflow Instead of Getting a Wrapped Value?

Use the checked methods in the `Math` class:

```java
int safeSum = Math.addExact(1_000_000_000, 1_000_000_000);
long safeProduct = Math.multiplyExact(100_000L, 100_000L);
int checkedNarrowing = Math.toIntExact(2_000_000_000L);
```

These declarations are valid inside a Java method; their results are `2_000_000_000`, `10_000_000_000`, and `2_000_000_000`, respectively. `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, and `Math.toIntExact` throw `ArithmeticException` on overflow or when narrowing goes out of range.

One thing to keep in mind: `Math.addExact` has both `int` and `long` overloads. If you want to add two values whose sum might exceed `int`, use at least one `long` operand to select the `long` operation:

```java
long total = Math.addExact(2_000_000_000L, 1_000_000_000L);
```

For numbers larger than the `long` range, switch to `java.math.BigInteger` instead of trying to use an out-of-bounds `long` literal:

```java
java.math.BigInteger veryLarge =
        new java.math.BigInteger("9223372036854775808");
```

This is an arbitrary-precision integer initialized from a string; it is **not** a `long` literal.

## 8. When Numbers Come from Strings, Does `L` Still Apply?

The `L` suffix is **Java source-code syntax**, not part of text-formatted numeric data. If the input is the string `"3000000000"`, use the appropriate parsing API:

```java
long number = Long.parseLong("3000000000"); // 3000000000L.
```

`Integer.parseInt("3000000000")` throws `NumberFormatException` because it exceeds `int`. `Long.parseLong("3000000000L")` also throws `NumberFormatException`, because the character `L` is not a valid decimal digit in a string. Similarly, the `_` separator is allowed in source-code literals like `3_000L`, but `Long.parseLong("3_000")` does not accept it.

To parse hexadecimal or binary text, provide the corresponding radix, such as `Long.parseLong("FF", 16)` returning 255. String-parsing APIs also have to handle malformed or out-of-range input; appending `L` to the end of a string should not be treated as a type-conversion step.

## 9. Common Errors and Fixes

| Case | Cause | Fix |
| --- | --- | --- |
| `long n = 3000000000;` | Unsuffixed decimal literal exceeds `int` | `long n = 3000000000L;` |
| `long n = 2147483648;` | Variable type does not decide literal type | `long n = 2147483648L;` |
| `long n = 9223372036854775808L;` | Exceeds `Long.MAX_VALUE` | Use `BigInteger` if that positive number is needed |
| `int n = 3000000000L;` | Valid `long` literal, but target is `int` | Choose `long` as the variable type; only narrow after checking |
| `long x = 100000 * 100000;` | `int` multiplication overflows before assignment | `100000L * 100000` |
| `long x = (long) (100000 * 100000);` | Casting an already overflowed result | Cast one operand before multiplying |
| `long x = Long.MAX_VALUE + 1L;` | `long` addition can still overflow | `Math.addExact` to detect; `BigInteger` if larger values are needed |
| `Long.parseLong("123L")` | `L` suffix belongs only to source-code syntax | `Long.parseLong("123")` |
| `0xFFFF_FFFF` mistaken as positive | 32-bit pattern has sign bit 1 so it is a negative `int` | Use `0xFFFF_FFFFL` if `4_294_967_295` is desired |
| `3_000_L` | Underscore placed between digit and suffix | `3_000L` |

## 10. Self-Check

1. **Is `long a = 5;` valid?** Yes. `5` is a valid `int` literal, which is widened to `long`.
2. **Is `long a = 2_147_483_648;` valid?** No. The unsuffixed decimal literal itself exceeds the `int` limit.
3. **Is `long a = -2_147_483_648;` valid?** Yes. Java permits the special case representing `Integer.MIN_VALUE`, then widens the result to `long`.
4. **What value does `long a = 2_147_483_647 + 1;` produce?** `-2_147_483_648`, because `int` addition overflows before assignment. If you want `2_147_483_648`, write `2_147_483_647L + 1`.
5. **Is `int x = 0xFFFF_FFFF;` valid?** Yes, `x == -1`. **`long y = 0xFFFF_FFFFL;`** has the value `4_294_967_295`.
6. **When is `L` not enough?** When the value exceeds even `long`, when the result of a `long` operation might overflow, or when you want to detect overflow via an exception. In those cases, use `BigInteger` or `Math`'s checked operations as needed.

**Remember:** `L` determines **the type of an integer literal as soon as source code is parsed**. The receiving variable's type cannot fix an already out-of-range literal, and assigning to `long` cannot recover an already overflowed `int` calculation. Choose a sufficiently wide type **before the operation**, and use overflow checking when exact calculation is a strict requirement.