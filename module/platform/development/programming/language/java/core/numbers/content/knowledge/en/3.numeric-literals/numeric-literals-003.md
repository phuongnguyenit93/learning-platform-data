# Decimal, Binary, Octal, and Hexadecimal in Java

## 1. One Value, Four Representations

An integer is a **value**, while a numeral system (*base* / *radix*) is **a way of writing that value**. For example, the integer forty-two can be written as:

| Numeral System | Base | Allowed Digits | Mathematical Notation for 42 | Java Integer Literal |
|---|---:|---|---|---|
| Decimal | 10 | 0–9 | \(42_{10}\) | `42` |
| Binary | 2 | 0, 1 | \(101010_2\) | `0b101010` |
| Octal | 8 | 0–7 | \(52_8\) | `052` |
| Hexadecimal | 16 | 0–9, A–F | \(2A_{16}\) | `0x2A` |

The literals `42`, `0b101010`, `052`, and `0x2A` all have the exact same **integer value 42**. Choosing a different base does not make an `int` variable larger, faster, or more precise: it only changes how source code represents a number.

When reading a literal, distinguish the **prefix** (indicating the numeral system), the **digits**, **underscores** (for readability), and the **`L` suffix** (indicating type `long`). These parts do not play the same role.

## 2. Principle of Positional Value Systems

For base \(b\), each position from right to left carries weight \(b^0, b^1, b^2,\ldots\). A sequence of digits \(d_nd_{n-1}\dots d_0\) represents:

\[
d_n b^n + d_{n-1}b^{n-1}+\cdots+d_1 b+d_0.
\]

Every digit \(d_i\) must satisfy \(0 \le d_i < b\). Base 16 additionally uses A = 10, B = 11, C = 12, D = 13, E = 14, F = 15; both uppercase and lowercase letters are accepted.

Applying this to the number 42:

- Decimal `42` = \(4\times10+2=42\).
- Binary `101010` = \(1\times32+0\times16+1\times8+0\times4+1\times2+0=42\).
- Octal `52` = \(5\times8+2=42\).
- Hex `2A` = \(2\times16+10=42\).

From this it is clear: you cannot deduce a value merely by looking at the digit sequence `10` while ignoring the base. `10` in base 2 equals 2; in base 8 it equals 8; in base 10 it equals 10; in base 16 it equals 16.

## 3. Java Integer Literal Syntax

### 3.1. Decimal — Default

A literal with no special prefix that starts with a digit 1–9 is interpreted as decimal; a standalone `0` is also valid:

```java
int ten = 10;
int thousand = 1_000;
long large = 3_000_000_000L;
int zero = 0;
```

Add the `L` or `l` suffix to indicate a `long` literal; **uppercase `L`** is preferred because it is easy to distinguish from the digit 1.

### 3.2. Binary — Prefix `0b` or `0B`

Supported since Java 7, using only 0 and 1:

```java
int flags = 0b1010;       // 10 decimal
int eight = 0B1000;       // 8 decimal
long wide = 0b1_0000L;   // 16 decimal
```

`0b102` is **invalid** because the digit 2 does not exist in base 2. No binary prefix implicitly marks a literal as `byte`: `0b1111_1111` is an `int` literal with value 255; `(byte) 0b1111_1111` produces the `byte` value -1.

### 3.3. Octal — Prefix **Digit 0**

Java writes octal using a **leading digit 0 at the start of the literal**, following historical syntax:

```java
int tenInOctal = 012;  // 1*8 + 2 = 10 decimal
int permission = 0755; // 7*64 + 5*8 + 5 = 493 decimal
int eight = 010;       // 8 decimal, NOT 10
```

This is a common pitfall: `010` **does not equal** `10`. Writing `08` or `09` causes a **compile error**, because 8 and 9 are not octal digits.

Java does **not** use a Python-style `0o` prefix to represent octal. If you want decimal 10, write `10`; if you need to express octal clearly in prose, write \(12_8\), while in Java use `012`.

### 3.4. Hexadecimal — Prefix `0x` or `0X`

Hex uses digits 0–9 and A–F (case-insensitive):

```java
int answer = 0x2A;          // 42 decimal
int byteMask = 0xFF;        // 255 decimal
int color = 0x12_AB_34;     // 1_223_476 decimal
long wide = 0X1_0000_0000L; // 4_294_967_296 decimal
```

Hex is convenient when working with bytes or bits: 1 hex digit corresponds to **4 bits**, and 2 hex digits correspond to **8 bits**. For example, `0xFF` = `0b1111_1111` = 255.

`0xG1` is invalid because G is not a hex digit. When writing integer hex literals, you can use letters A–F in either case; Java treats `0x2a` and `0X2A` identically.

## 4. Underscores, Suffixes, and Literal Types

Java allows underscores **between digits** to improve readability:

```java
int population = 2_147_483_647;
int bits = 0b1010_0101;
int code = 0xCAFE_BABE;
long id = 0xFFFF_FFFF_FFFF_FFFFL;
```

Underscores do not change the value. The following forms are **invalid**:

```java
// int bad1 = _123;      // '_' cannot be at the start of a literal
// int bad2 = 123_;      // '_' cannot be at the end of a literal
// int bad3 = 0x_FF;     // '_' cannot be immediately after the prefix
// int bad4 = 0b_1010;   // '_' cannot be immediately after the prefix
// long bad5 = 123_L;    // '_' cannot precede the L suffix
```

These lines are all commented out so the sample program does not encounter compile errors. Add the `L` suffix to an integer literal to choose type `long`; the `0b`, `0`, and `0x` prefixes only choose the **base**, not `byte`/`short` or `long`.

For an integer literal without `L`, the type is `int`; with `L`, the type is `long`, within the valid range of the notation. Java permits a few special decimal integer constants as unary minus expressions for the minimum values, such as `-2147483648`; normally use `Integer.MIN_VALUE` and `Long.MIN_VALUE` to avoid confusing the bounds.

**Note when assigning to smaller variables:** Java allows `byte b = 0x7F;` because it is an `int` constant expression whose value 127 fits in `byte`. That does not mean `0x7F` has type `byte`. `byte b = 0xFF;` is a compile error because 255 is outside the `byte` range, unless explicitly cast.

## 5. Program Demonstrating Four Notations Are the Same Number

Save the file `RadixLiteralDemo.java`:

```java
public class RadixLiteralDemo {
    public static void main(String[] args) {
        int decimal = 42;
        int binary = 0b101010;
        int octal = 052;
        int hex = 0x2A;

        System.out.println(decimal == binary
                && binary == octal
                && octal == hex);
        System.out.println("decimal: " + decimal);
        System.out.println("binary: " + Integer.toBinaryString(decimal));
        System.out.println("octal: " + Integer.toOctalString(decimal));
        System.out.println("hex: " + Integer.toHexString(decimal));
        System.out.println("010 in Java = " + 010);
        System.out.println("0xFF = " + 0xFF);
        System.out.println("0b11111111 = " + 0b11111111);
    }
}
```

Compile and run with Java 17+:

```bash
javac RadixLiteralDemo.java
java RadixLiteralDemo
```

Exact output:

```text
true
decimal: 42
binary: 101010
octal: 52
hex: 2a
010 in Java = 8
0xFF = 255
0b11111111 = 255
```

`Integer.toBinaryString`, `toOctalString`, and `toHexString` **return digit strings**, without automatically prepending source prefixes `0b`/`0`/`0x`. Hex strings use lowercase a–f by default.

## 6. Relationship Between Numeral Systems, Bits, and Signed Numbers

### 6.1. Grouping Bits to Convert to Hex or Octal

Because \(16=2^4\), split a binary representation into **groups of 4 bits from right to left** to convert to hex:

```text
binary:       0010 1010
hex digits:      2    A
hex:             0x2A
```

Because \(8=2^3\), split binary into **groups of 3 bits from right to left** to convert to octal:

```text
binary:     101 010
oct digits:   5   2
octal:        052
```

If the leftmost group has fewer than 4 or 3 bits, simply pad with 0s on **the left of the positive number's representation** for readability without changing the value.

### 6.2. The Base Does Not Remove Signed Integer Rules

`int` always has 32 bits, and `long` always has 64 bits. The representation for signed integers in Java is **two's complement**.

Therefore, a full 32-bit non-decimal literal whose highest bit is 1 can carry a **negative** `int` value:

```java
int allOnes = 0xFFFF_FFFF;        // -1 as a 32-bit int
int lowest = 0x8000_0000;        // Integer.MIN_VALUE
long positive = 0xFFFF_FFFFL;    // 4294967295L (64-bit)
long longAllOnes = 0xFFFF_FFFF_FFFF_FFFFL; // -1 as a long
```

The difference between `0xFFFF_FFFF` and `0xFFFF_FFFFL` is **the `L` suffix**: the same hex digits are represented as an `int` or a `long` value. For `int`, 32 bits all equal to 1 is -1; for `long`, that same 32-bit pattern is extended with leading 0 bits, so it is positive 4_294_967_295.

In particular, `0xFFFF_FFFF` **does not hold the positive value 4_294_967_295** when stored as a signed `int`. If you need an unsigned 32-bit interpretation, you can use `Integer.toUnsignedLong(int)` or `Integer.toUnsignedString(int)`.

### 6.3. One Bit Sequence Has Multiple Interpretations

For example, the 8 bits `1111_1111` can be:

- **255** if interpreted as unsigned 8-bit.
- **-1** if interpreted as a signed `byte` using two's complement.

In Java, the literal `0b1111_1111` is initially the `int` 255. The cast `(byte) 0b1111_1111` keeps the low 8 bits and interprets them as a signed `byte`, yielding -1.

Do not confuse this with **base conversion**. Converting from `0xFF` to `0b1111_1111` only changes how the same number 255 is written; casting to `byte` can change the value because it changes **the data type's range**.

## 7. Converting Numbers to Strings and Parsing Strings by Base

Literals are used when writing **source code**. Data read from users, files, or networks is **runtime strings**, requiring conversion APIs. Java provides:

| Need | Common API | Example Result |
|---|---|---|
| Integer → binary | `Integer.toBinaryString(42)` | `"101010"` |
| Integer → octal | `Integer.toOctalString(42)` | `"52"` |
| Integer → hex | `Integer.toHexString(42)` | `"2a"` |
| Integer → string in custom base | `Integer.toString(42, 16)` | `"2a"` |
| Binary string → `int` | `Integer.parseInt("101010", 2)` | 42 |
| Octal string → `int` | `Integer.parseInt("52", 8)` | 42 |
| Hex string → `int` | `Integer.parseInt("2A", 16)` | 42 |
| Decimal string → `int` | `Integer.parseInt("42", 10)` | 42 |

`Integer.parseInt(String, int)` and `Integer.toString(int, int)` support radixes **2 through 36**. For bases greater than 10, Java uses the letters a–z for additional digits as needed.

**Prefix pitfall:** `Integer.parseInt("0x2A", 16)` throws `NumberFormatException` because `parseInt` expects **digits belonging to the radix** (optionally with a sign) and does not strip a `0x` prefix like Java source syntax. `Integer.decode("0x2A")` can accept the `0x` prefix; `Integer.decode("052")` interprets it as octal, while `Integer.decode("42")` interprets it as decimal. `Integer.decode` does not accept the binary prefix `0b`.

Do not call `Integer.parseInt("052")` by default expecting 42: the overload without a radix argument reads **decimal**, so the result is 52.

### Runnable Example: Parsing and Formatting

Save `RadixConversionDemo.java`:

```java
public class RadixConversionDemo {
    public static void main(String[] args) {
        int fromBinary = Integer.parseInt("101010", 2);
        int fromOctal = Integer.parseInt("52", 8);
        int fromHex = Integer.parseInt("2A", 16);

        System.out.println(fromBinary + ", " + fromOctal + ", " + fromHex);
        System.out.println(Integer.toString(42, 16));
        System.out.println(Integer.decode("0x2A"));
        System.out.println(Integer.parseInt("052"));
        System.out.println(Integer.toUnsignedLong(0xFFFF_FFFF));

        try {
            Integer.parseInt("0x2A", 16);
        } catch (NumberFormatException e) {
            System.out.println("parseInt: invalid prefix");
        }
    }
}
```

Run:

```bash
javac RadixConversionDemo.java
java RadixConversionDemo
```

Output:

```text
42, 42, 42
2a
42
52
4294967295
parseInt: invalid prefix
```

If the number exceeds the `int` range, use `Long.parseLong` when it fits in `long`; for even larger numbers, use `new java.math.BigInteger("FF...", 16)` and explicitly pass the proper radix. `BigInteger(String, radix)` also takes a string of digits in the given radix and does not automatically handle Java literal prefixes.

## 8. How to Print Numeric Values by Base

`System.out.println(number)` prints integers in **decimal**. When you want to print binary/octal/hex, use the conversion methods above or `printf`.

```java
int n = 42;
System.out.printf("dec=%d, oct=%o, hex=%x, HEX=%X%n", n, n, n, n);
```

Output:

```text
dec=42, oct=52, hex=2a, HEX=2A
```

In `printf`, `%d` is decimal, `%o` is octal, `%x`/`%X` is hex. **`%b` does NOT mean binary** in Java's `Formatter`; it is the boolean format specifier. To print binary, use `Integer.toBinaryString(n)` or `Long.toBinaryString(n)`.

When printing negative numbers with `toBinaryString`/`toHexString`, the output reflects the **unsigned two's complement bit pattern** of the corresponding type; for example, `Integer.toHexString(-1)` returns `"ffffffff"`, not `"-1"`. If you need a signed representation in a given base, use `Integer.toString(value, radix)`: `Integer.toString(-1, 16)` returns `"-1"`.

You must also distinguish **text display** from **binary encoding**. The string `"FF"` contains two F characters and does not automatically become a single byte `0xFF`. You must parse according to the radix and then choose the appropriate way to write bytes.

## 9. Typical Errors and How to Handle Them

| Symptom | Cause | How to Handle |
|---|---|---|
| `010` yields 8 instead of 10 | Leading 0 turns the literal into octal | Write `10` if you want decimal ten |
| `08` fails to compile | Digit 8 does not belong to base 8 | Remove leading 0 or fix the digit |
| `0o12` fails to compile | Java does not have a `0o` prefix | Use `012` |
| `0b102` fails to compile | 2 is invalid in base 2 | Write only 0 and 1 |
| `0xGG` fails to compile | G is not among hex digits | Write only 0–9 and A–F |
| `0x_FF` fails to compile | Underscore adjacent to prefix | Write `0xFF` or `0xF_F` |
| `0xFFFF_FFFF` becomes -1 | Signed 32-bit int bit pattern | Use `0xFFFF_FFFFL` or unsigned APIs where appropriate |
| `Integer.parseInt("FF")` throws error | Parses decimal by default | Pass radix 16 |
| `Integer.parseInt("0xFF",16)` throws error | `parseInt` does not accept `0x` | Use `"FF"` with radix 16 or `Integer.decode` |
| `printf("%b", 42)` prints `true` | `%b` is the boolean formatter | Use `Integer.toBinaryString(42)` |

An integer stores the same bits regardless of which base you wrote the literal in. When manipulating bitmasks, **hex is easy to read by byte**; when inspecting individual bits, **binary is visual**; octal is commonly seen in legacy formats/conventions; decimal is easy to read for business data. Choose the notation that suits the reader and data format.

## 10. Self-Check Exercises

**Exercise 1.** Are `0b1111`, `017`, `15`, and `0xF` equal?  
**Answer:** Yes, all four equal 15 in decimal.

**Exercise 2.** Do `010` and `10` have the same value?  
**Answer:** No; `010` = 8 decimal, `10` = 10 decimal.

**Exercise 3.** Convert `0x3C` to binary and decimal.  
**Answer:** `0b0011_1100` (leading zeros can be omitted as `0b11_1100`), which equals \(3\times16+12=60\).

**Exercise 4.** Why does `Integer.toBinaryString(-1)` output 32 `1` digits, while `Integer.toString(-1, 2)` outputs `"-1"`?  
**Answer:** The first method presents the **two's complement bit pattern** of a 32-bit `int`; the second method represents the **signed numeric value** in base 2.

**Exercise 5.** Which API should be used to parse the string `"11111111"` into the numeric value 255?  
**Answer:** `Integer.parseInt("11111111", 2)`. If subsequently cast to `byte`, the value becomes -1 because of the `byte` type range.

**Exercise 6.** Does `0xFFFF_FFFFL` differ from `0xFFFF_FFFF`?  
**Answer:** Yes; the `L` form is a positive `long` 4_294_967_295, while the unsuffixed form is `int` -1.

**Exercise 7.** Why does `Integer.parseInt("052")` return 52 while the literal `052` in source code is 42?  
**Answer:** `parseInt` without a radix defaults to **decimal**, whereas a literal with a leading zero uses **octal**.

**Remember:** The base determines how *digits are written/read*; the data type determines *the numeric range and bit width*. In Java: **decimal** is written normally, **binary** starts with `0b`, **octal** starts with `0`, and **hex** starts with `0x`. When processing external strings, pass the radix explicitly and check the value range before casting.