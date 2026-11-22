# Integer Literals and the Default `int` Type in Java

**Integer literals** are whole numbers written directly in Java source code: `42`, `0b101010`, `052`, `0x2A`. These notations use different radixes (bases) but represent the same decimal value 42. **By default, an integer literal without an `L` suffix has type `int`; with an `L` (or `l`) suffix, it has type `long`.** The base does not determine the type. The range and meaning of decimal and non-decimal literals have several differences that learners must master.

This lesson covers *literals and compile-time expression types*, not *default field values* or *runtime string parsing*.

## 1. The Four Bases of Integer Literals

| Form | Leading Notation | Valid Digits | Example | Decimal Value |
| --- | --- | --- | --- | --- |
| Decimal (base 10) | No special prefix; ordinary numbers | `0` to `9` | `42` | 42 |
| Binary (base 2) | `0b` or `0B` | `0`, `1` | `0b101010` | 42 |
| Octal (base 8) | A `0` at the start of a multi-digit literal | `0` to `7` | `052` | 42 |
| Hexadecimal (base 16) | `0x` or `0X` | `0`–`9` and `A`–`F` (case-insensitive) | `0x2A` | 42 |

```java
int decimal = 42;      // 42
int binary = 0b101010; // 32 + 8 + 2 = 42
int octal = 052;       // 5 * 8 + 2 = 42
int hex = 0x2A;        // 2 * 16 + 10 = 42
```

This is an **assignment illustration snippet**, not a standalone class. After compilation, all variables hold the integer value 42. The program does not retain the "typed base" inside the `int` value. Therefore, `System.out.println(0x2A)` prints `42` by default, rather than automatically printing `0x2A`.

Base 2 is useful when inspecting bitmasks, base 16 helps group bits for bytes and status flags, and base 10 is convenient for ordinary quantities. Base 8 is used less often because a leading `0` easily creates a pitfall.

## 2. Default `int` Type and the `L` Suffix for `long`

All four notations `7`, `0b111`, `07`, and `0x7` have **type `int`**. Appending `L` creates a literal of **type `long`**: `7L`, `0b111L`, `07L`, `0x7L`.

| Literal | Type | Value |
| --- | --- | --- |
| `100`, `0b1100100`, `0144`, `0x64` | `int` | 100 |
| `100L`, `0b1100100L`, `0144L`, `0x64L` | `long` | 100 |
| `0xFFFF_FFFF` | `int` | -1 |
| `0xFFFF_FFFFL` | `long` | 4294967295 |

Lowercase `l` is also valid, but you should use **uppercase `L`** to avoid confusing it with `1`.

An `int` literal can be *widened* when assigned to a `long` as long as its value is valid:

```java
long a = 100;              // int literal then widened to long
long b = 100L;             // long literal from the start
long c = 2_147_483_648L;   // requires L suffix because it exceeds max int
// long bad = 2_147_483_648; // compile error: decimal int literal too large
```

**The target variable's type does not change how the literal is parsed.** `long bad = 3000000000;` is invalid, even though variable `bad` has type `long`. You must write `3_000_000_000L`. The `L` suffix belongs to the literal itself and does not retroactively apply to an addition or multiplication already performed earlier.

One way to demonstrate literal types is by using method overloading:

```java
static String category(int value) {
    return "int";
}
static String category(long value) {
    return "long";
}
// category(42)  -> "int"
// category(42L) -> "long"
```

These two methods are **declarations inside a class**, not standalone code. `42` selects the `int` overload; `42L` selects the `long` overload.

## 3. Range of Decimal Literals and the Unary Minus Sign

The `int` primitive has a range from `-2_147_483_648` to `2_147_483_647`; the `long` primitive has a range from `-9_223_372_036_854_775_808L` to `9_223_372_036_854_775_807L`.

Ordinary unsuffixed **decimal** literals accept values from `0` to `2_147_483_647`. Java makes an exception for the token `2147483648` when it is the operand of the unary minus operator `-`, allowing you to write `-2147483648`, which is `Integer.MIN_VALUE`. A similar exception applies to `9223372036854775808L` in `-9223372036854775808L`.

```java
int max = 2_147_483_647;
int min = -2_147_483_648;
long maxLong = 9_223_372_036_854_775_807L;
long minLong = -9_223_372_036_854_775_808L;

// int badInt = 2_147_483_648;  // error if not the operand of a unary minus
// long badLong = 9_223_372_036_854_775_808L; // error if not the operand of a unary minus
```

Syntactically, `-42` consists of **operator `-`** and **literal `42`**; the minus sign is not part of the literal token. This is why the minimum value of an integer type requires a language exception. If the goal is to state the bounds explicitly, you can use `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `Long.MIN_VALUE`, and `Long.MAX_VALUE`.

## 4. Hex/Binary Literals Are Interpreted as Signed Bit Patterns

Non-decimal literals (binary, octal, hex) represent **bit patterns**. A literal without `L` must fit within 32 bits for `int`; with `L`, it has a 64-bit width for `long`. When the sign bit is set, *two's complement* interpretation produces a negative value.

| Literal | Type | Value |
| --- | --- | --- |
| `0x7FFF_FFFF` | `int` | 2147483647 |
| `0x8000_0000` | `int` | -2147483648 |
| `0xFFFF_FFFF` | `int` | -1 |
| `0b11111111_11111111_11111111_11111111` | `int` | -1 |
| `0xFFFF_FFFFL` | `long` | 4294967295 |
| `0x1_0000_0000L` | `long` | 4294967296 |

Example:

```java
int allBitsOne = 0xFFFF_FFFF;   // -1: all 32 bits are 1
int signBit = 0x8000_0000;     // -2147483648
long positive = 0xFFFF_FFFFL;  // 4294967295 (in 64 bits)
// int invalid = 0x1_0000_0000; // error: requires 33 bits
```

**Do not treat `0xFFFF_FFFF` as a positive `int` equal to 4294967295.** It is a signed 32-bit pattern and therefore has value `-1`. If you need the corresponding positive value, add `L` to the literal before performing calculations.

Another case: `-0x8000_0000` still equals `-2147483648` when the expression has type `int`, because negating the minimum `int` value overflows and wraps back to itself. Write `0x8000_0000L` if you want the positive value 2147483648L.

## 5. Separating Digits with Underscores

Since Java 7, you can place `_` **between digits** of an integer literal for readability. Underscores do not change the value, base, or type.

```java
int count = 1_000_000;
int bits = 0b1010_1100;
int rgb = 0x00FF_80A0;
long distance = 9_000_000_000L;
```

The examples below **illustrate compile errors when uncommented**:

```java
// int a = _100;   // '_' cannot precede the first digit
// int b = 100_;   // '_' cannot follow the last digit
// int c = 0x_FF;  // '_' cannot be adjacent to the 0x prefix
// int d = 0b_101; // '_' cannot be adjacent to the 0b prefix
// long e = 123_L; // '_' cannot precede the L suffix
```

Useful groupings: groups of three decimal digits (`1_000_000`), groups of four bits (`0b1100_1010`), groups of two or four hex digits (`0xCA_FE`). The `_` character in variable names follows different rules; here we only discuss characters inside numeric tokens.

## 6. Leading-Zero Pitfall: Octal, Not Zero-Padding

In Java, `010` is a **base-8** literal, so it equals `8` in decimal. `077` equals `63`. The digits `8` and `9` are invalid after a leading `0` that starts an octal literal.

```java
int a = 010; // 8
int b = 077; // 63
int c = 10;  // 10
// int invalid08 = 08; // compile error
// int invalid09 = 09; // compile error
```

Distinguish numbers written in **source code** from strings **parsed at runtime**:

| Expression | Result | Why |
| --- | --- | --- |
| `010` | `8` | Octal literal |
| `Integer.parseInt("010")` | `10` | `parseInt` defaults to base 10 |
| `Integer.parseInt("010", 8)` | `8` | Base 8 passed explicitly |
| `Integer.parseInt("2A", 16)` | `42` | Parses two hex digits |
| `Integer.decode("010")` | `8` | `decode` interprets a leading 0 as octal |
| `Integer.decode("0x2A")` | `42` | `decode` interprets the 0x prefix as hex |

Note: `Integer.parseInt("0x2A", 16)` does not accept the `0x` prefix; `Integer.decode("0x2A")` is more suitable if the string already contains a base prefix. Do not confuse these string-parsing methods with the compiler's literal syntax.

## 7. Operations, Overflow, and Type Conversion

With two `int` operands, integer addition is normally performed **in type `int`**; converting the result into a `long` variable only happens afterward:

```java
long overflowed = 2_147_483_647 + 1; // int overflows first -> -2147483648L
long correct = 2_147_483_647L + 1;  // long + int -> 2147483648L
```

Similarly, `long product = 100_000 * 100_000;` performs `int` multiplication before widening, which can overflow; use `100_000L * 100_000` if you need an accurate `long` product.

"Literals default to `int`" **does not prevent** assigning an `int` constant within range to `byte`, `short`, or `char`. Java allows narrowing conversion in assignment contexts for certain **compile-time constant expressions**:

```java
byte small = 127;      // valid: int value 127 fits in byte
short sh = 30_000;     // valid: fits in short
char letter = 65;      // valid: character 'A'
byte sum = 1 + 2;      // valid: constant expression equals 3
long widened = 100;    // valid: widening int -> long

// byte tooBig = 128;  // error: does not fit in byte
// short tooBigShort = 40_000; // error: does not fit in short
```

An ordinary `int` variable differs from a constant expression:

```java
int local = 10;
// byte wrong = local; // error: no automatic narrowing from an int variable

final int fixed = 10; // constant variable, initializer is a constant expression
byte ok = fixed;       // valid because the value is within byte range
byte narrowed = (byte) 0xFF; // -1: explicit cast truncates bits
```

For `byte`, if you need to interpret the bits as an **unsigned** number from 0 to 255, `Byte.toUnsignedInt(narrowed)` gives `255`. This is an operation that reads the bit value; it does not create an `unsigned byte` primitive type in Java.

## 8. Complete Runnable Java 17+ Example

Create the file **`IntegerLiteralDemo.java`**:

```java
public class IntegerLiteralDemo {
    static String kind(int value) {
        return "int";
    }

    static String kind(long value) {
        return "long";
    }

    public static void main(String[] args) {
        int decimal = 42;
        int binary = 0b101010;
        int octal = 052;
        int hexadecimal = 0x2A;

        System.out.println("decimal=" + decimal);
        System.out.println("binary=" + binary);
        System.out.println("octal=" + octal);
        System.out.println("hexadecimal=" + hexadecimal);
        System.out.println("42 type=" + kind(42));
        System.out.println("42L type=" + kind(42L));
        System.out.println("octal010=" + 010);
        System.out.println("parse010=" + Integer.parseInt("010"));
        System.out.println("parse2A=" + Integer.parseInt("2A", 16));
        System.out.println("allBitsInt=" + 0xFFFF_FFFF);
        System.out.println("allBitsLong=" + 0xFFFF_FFFFL);
        System.out.println("minIntHex=" + 0x8000_0000);

        long overflowed = 2_147_483_647 + 1;
        long correct = 2_147_483_647L + 1;
        System.out.println("overflowed=" + overflowed);
        System.out.println("correct=" + correct);

        byte narrow = (byte) 0xFF;
        System.out.println("narrow=" + narrow);
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac IntegerLiteralDemo.java
java IntegerLiteralDemo
```

Exact output:

```text
decimal=42
binary=42
octal=42
hexadecimal=42
42 type=int
42L type=long
octal010=8
parse010=10
parse2A=42
allBitsInt=-1
allBitsLong=4294967295
minIntHex=-2147483648
overflowed=-2147483648
correct=2147483648
narrow=-1
```

Observations from the output: different base prefixes do not change the value 42; the `L` suffix changes the literal type and affects overloading; all-1 bits in `int` are interpreted as -1; `int` addition can overflow before being assigned to `long`.

## 9. Common Mistakes and How to Read a Literal

| Mistake or Misconception | Issue | Fix |
| --- | --- | --- |
| `long x = 3000000000;` | Unsuffixed decimal literal exceeds `int` | `long x = 3_000_000_000L;` |
| `int x = 09;` | 9 is not a valid octal digit | `int x = 9;` |
| `int mask = 0x1_0000_0000;` | Requires more than 32 bits to represent | Use `long mask = 0x1_0000_0000L;` |
| Expecting `0xFFFF_FFFF` to equal 4294967295 | It is a signed 32-bit `int` pattern | Use `0xFFFF_FFFFL` if a positive value is needed |
| `long n = 2_147_483_647 + 1;` gives a negative number | Overflow in `int` addition before widening | `long n = 2_147_483_647L + 1;` |
| `byte b = 128;` | `int` constant exceeds `byte` range | Choose a suitable type or recheck the data |
| `0x_FF` causes an error | Underscore placed right after prefix | `0xFF` or `0xF_F` |
| Confusing `"010"` with `010` | Strings use parsing APIs; literals are parsed by the compiler | Specify the radix explicitly when parsing strings |

When encountering a literal, inspect it in this order:

1. **Prefix:** `0b` → binary, `0x` → hex, leading `0` before digits → octal, otherwise → decimal.
2. **Suffix:** has `L` → `long`; no suffix → `int`, keeping in mind the limits and the `-2147483648` exception.
3. **Bit value:** non-decimal literals with the sign bit set represent negative numbers in `int`/`long`.
4. **Expression context:** `int` arithmetic can overflow before the value is assigned to `long`.
5. **Target type:** constants can conditionally narrow to `byte`/`short`/`char`, whereas `int` variables cannot automatically do so.

**Key takeaway:** `42`, `0b101010`, `052`, and `0x2A` are all `int` literals with value 42. You need `L` to create a `long` literal; the base prefix governs how digits are read, while the sign bit, type rules, and expression determine the final result.