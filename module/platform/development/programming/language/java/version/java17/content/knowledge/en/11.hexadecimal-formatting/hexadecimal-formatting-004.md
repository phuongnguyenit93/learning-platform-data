# Separators, Prefixes, and Suffixes for Hexadecimal Literals in Java 17

Java allows writing integers and floating-point numbers in hexadecimal (base 16) directly in source code. This notation commonly appears when working with bytes, bit masks, colors, status codes, binary data, addresses, or values where each group of bits needs to be represented clearly.

A hexadecimal literal can have three components to recognize:

- **Prefix** `0x` or `0X`: indicates that the following digits are read in base 16.
- **Separator** `_`: groups digits for readability; does not change the value.
- **Suffix** such as `L` for integers or `F`/`D` for floating-point numbers: specifies the literal type in the corresponding cases.

This lesson focuses on the syntax applicable in Java 17, how to read values, underscore placement restrictions, the difference between `int` and `long`, hex floating-point literals, and how to convert base-16 strings at runtime.

## 1. Recognizing Hexadecimal Digits and Prefixes

Hexadecimal uses 16 symbols:

| Symbol | Decimal value | Symbol | Decimal value |
|---|---:|---|---:|
| `0` | 0 | `8` | 8 |
| `1` | 1 | `9` | 9 |
| `2` | 2 | `A` or `a` | 10 |
| `3` | 3 | `B` or `b` | 11 |
| `4` | 4 | `C` or `c` | 12 |
| `5` | 5 | `D` or `d` | 13 |
| `6` | 6 | `E` or `e` | 14 |
| `7` | 7 | `F` or `f` | 15 |

Each position has a weight equal to a power of 16. For example:

```text
0x2A = 2 × 16 + 10 = 42
0x100 = 1 × 16² = 256
0xFF = 15 × 16 + 15 = 255
```

In Java, the hexadecimal prefixes are:

- `0x` — lowercase `x`.
- `0X` — uppercase `X`.

Example:

~~~java
int decimal = 42;
int hexLower = 0x2a;
int hexUpper = 0X2A;

System.out.println(decimal); // 42
System.out.println(hexLower); // 42
System.out.println(hexUpper); // 42
~~~

All three variables hold the same value. The `0x` prefix is not stored in the numeric value; it only tells the compiler how to read the literal in source code.

Do not use forms like `0h2A`, `#2A`, or `2Ah` to write hexadecimal integer literals in Java. Those forms may appear in other languages or formats, but they are not valid Java integer literal syntax.

### 1.1. Distinguishing Hexadecimal Literals from Decimal Numbers

~~~java
int a = 26;    // Base 10
int b = 0x1A;  // Base 16: 1 × 16 + 10 = 26
int c = 032;   // Base 8: 3 × 8 + 2 = 26
int d = 0b11010; // Base 2: 16 + 8 + 2 = 26
~~~

Output:

~~~text
a = 26
b = 26
c = 26
d = 26
~~~

Values in memory do not carry a "base 16" or "base 10" tag. The radix only affects how the literal is written or how a number is formatted/parsed.

## 2. Digit Separators Using Underscores

Java allows using the underscore `_` inside numeric literals to group digits. This is useful when a literal is long or organized by bytes or words.

Example:

~~~java
int color = 0xFF_33_66;
int flags = 0b1010_0001;
long addressMask = 0x0000_FFFF_FFFF_FFFFL;
~~~

The following literals have the same value as their versions without underscores:

~~~java
int a = 0xFF33;
int b = 0xFF_33;
int c = 0xF_F_3_3;
~~~

The `_` character is purely for human readers. The compiler ignores it when parsing the literal; it does not add bits or alter the value.

### 2.1. Placing Separators Between Digits

Valid examples:

~~~java
int a = 0xCA_FE;
int b = 0xDEAD_BEEF;
long c = 0x1234_5678_9ABC_DEF0L;
int d = 0x1_0000;
~~~

Multiple consecutive underscores are permitted as long as they remain between digits:

~~~java
int value = 0xCA__FE;
~~~

Although valid, avoid overusing consecutive underscores because it reduces readability. A single separator between meaningful groups is usually clearer.

### 2.2. Where Underscores Cannot Be Placed

An underscore must be placed **between digits**. Do not place it at the start or end of a literal, adjacent to the prefix, or adjacent to the suffix.

| Syntax | Valid? | Reason |
|---|---|---|
| `0xCA_FE` | Yes | Separator is between digits |
| `0xDEAD_BEEF` | Yes | Valid digit grouping |
| `0x__CAFE` | No | Separator immediately follows the prefix |
| `0x_CAFE` | No | Separator immediately follows the prefix |
| `0xCAFE_` | No | Literal ends with a separator |
| `0xCAFE_L` | No | Separator is immediately before the suffix |
| `0xCA.FE` | Not an integer literal | A dot is not used to group integer digits |

Invalid examples:

~~~java
// The following lines do not compile:
int a = 0x_FF;
int b = 0xFF_;
long c = 0xCAFE_L;
~~~

Valid examples:

~~~java
int a = 0xFF;
long b = 0xCAFEL;
long c = 0xCA_FEL;
~~~

The suffix must be immediately adjacent to the literal, with no separator or whitespace in between. The `L` follows the last digit; `_` may only be used between digits.

### 2.3. Separators in Literals with a Suffix

When a suffix is present, the last digit must immediately precede the suffix; do not place a separator between the last digit and the suffix.

~~~java
long a = 0xCA_FE_L; // Invalid
~~~

Correct form:

~~~java
long value = 0xCA_FEL;
long mask = 0x00FF_FFFFL;
~~~

In `0xCA_FEL`, the last digit is `E`, followed directly by the `L` suffix. The `_` is between `A` and `F`, so it is valid.

## 3. Suffixes for Hexadecimal Integer Literals

Java has two primary integer types:

- `int`: 32-bit signed integer.
- `long`: 64-bit signed integer.

For hexadecimal integer literals, the suffix `L` or `l` specifies the `long` type. Prefer uppercase `L` because lowercase `l` is easily confused with the digit `1`.

~~~java
int intValue = 0x7FFF;
long longValue = 0x7FFF_FFFFL;
~~~

Without the `L` suffix, the compiler determines `int` or `long` based on literal rules and representable values. When you explicitly intend a `long` value, write `L`.

### 3.1. The L Suffix Changes the Literal Type

~~~java
int a = 0xFF;
long b = 0xFFL;

System.out.println(a); // 255
System.out.println(b); // 255
~~~

The numeric values in both variables are equal, but their types differ:

~~~java
System.out.println(((Object) a).getClass()); // class java.lang.Integer
System.out.println(((Object) b).getClass()); // class java.lang.Long
~~~

The `L` suffix does not make a number hexadecimal; the `0x` prefix indicates the radix. The suffix only specifies the integer type of the literal.

### 3.2. When Is the L Suffix Needed?

For example, a value requiring more than 32 bits to represent while fitting within the `long` range; the `L` suffix makes the intended type clear:

~~~java
long fileSize = 0x1_0000_0000L;
~~~

The value is 4,294,967,296. If a literal exceeds the `int` range, the compiler cannot treat it as `int` without `L` (compile-time error for an out-of-range `int` literal); adding `L` makes the intent explicit and avoids confusion about bit interpretation.

Use `L` when:

- The literal is used in operations with `long`.
- The value or mask requires 64 bits.
- You want to make the data type explicit in an API.
- You are declaring 64-bit size, offset, or mask constants.

Example:

~~~java
long mask64 = 0xFFFF_FFFF_FFFF_FFFFL;
long address = 0x0000_7FFF_FFFF_FFFFL;
~~~

### 3.3. There Is No U Suffix for Integer Literals

Java does not have a `U` or `UL` suffix like some languages to declare unsigned integer literals.

The primitives `byte`, `short`, `int`, and `long` are signed types. Java provides several APIs to interpret or manipulate unsigned values, for example:

~~~java
int bits = 0xFFFF_FFFF;

System.out.println(bits); // -1
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
System.out.println(Integer.toUnsignedLong(bits));   // 4294967295
~~~

The 32-bit value still has all bits set to 1. When read as a signed `int`, the result is `-1`; when interpreted as unsigned, the corresponding value is 4,294,967,295.

Do not write `0xFFFF_FFFFU` in Java; that is not valid syntax.

## 4. Understanding How Base-16 Literals Are Interpreted as int/long

An important aspect of non-decimal literals is that high bits can produce negative values under *two's complement* representation.

Example:

~~~java
int a = 0x7FFF_FFFF;
int b = 0x8000_0000;
int c = 0xFFFF_FFFF;

System.out.println(a); // 2147483647
System.out.println(b); // -2147483648
System.out.println(c); // -1
~~~

In 32 bits:

- `0x7FFF_FFFF`: highest bit is 0, the maximum positive `int` value.
- `0x8000_0000`: highest bit is 1, representing the minimum negative `int` value.
- `0xFFFF_FFFF`: all bits are 1, representing `-1`.

If you add the `L` suffix, the literal is interpreted at 64-bit width:

~~~java
long a = 0x8000_0000L;
long b = 0xFFFF_FFFFL;

System.out.println(a); // 2147483648
System.out.println(b); // 4294967295
~~~

This is very important when reading binary data or bit masks. With the same hex digits, choosing `int` versus `long` can change the interpreted value.

### 4.1. Comparing int and long Forms

| Literal | Type | Value |
|---|---|---:|
| `0x7FFF_FFFF` | `int` | 2,147,483,647 |
| `0x8000_0000` | `int` | -2,147,483,648 |
| `0xFFFF_FFFF` | `int` | -1 |
| `0x8000_0000L` | `long` | 2,147,483,648 |
| `0xFFFF_FFFFL` | `long` | 4,294,967,295 |
| `0xFFFF_FFFF_FFFF_FFFFL` | `long` | -1 |

If you want to preserve the bit pattern while printing it as unsigned, use unsigned APIs instead of expecting a `U` literal suffix.

### 4.2. Be Careful When Assigning to byte or short

Base-16 literals are often used to represent a byte:

~~~java
byte value = (byte) 0xFF;
System.out.println(value); // -1
~~~

`0xFF` is an `int` literal with value 255. The `byte` type only has the range `-128..127`, so an explicit cast is required. After casting, the low 8 bits are kept and interpreted as a signed byte, yielding `-1`.

Similarly:

~~~java
short value = (short) 0xFFFF;
System.out.println(value); // -1
~~~

Do not omit the cast in bit-manipulation examples. It makes the narrowing from 32 bits down to 8 or 16 bits explicit.

## 5. Hexadecimal Floating-Point Literals

Java also supports floating-point numbers written in hexadecimal. Unlike integer literals, hex floating-point literals require an exponent component using the letter `p` or `P`.

Example:

~~~java
double a = 0x1.0p0;
double b = 0x1.8p1;
double c = 0x1.0p-2;

System.out.println(a); // 1.0
System.out.println(b); // 3.0
System.out.println(c); // 0.25
~~~

How to read it:

- `0x`: base-16 prefix.
- `1.8`: base-16 significand.
- `p1`: multiply by 2 raised to the power 1.
- `p-2`: multiply by 2 raised to the power -2.

Example `0x1.8p1`:

```text
1.8 (base 16) = 1 + 8/16 = 1.5
p1            = multiply by 2¹ = 2
Result        = 1.5 × 2 = 3.0
```

**The letter `p` denotes a base-2 exponent**, not base 10. This is a key difference from decimal notation such as `1.5e1`.

### 5.1. Why Does Hex Floating-Point Require p/P?

Valid examples:

~~~java
double a = 0x1p2;
double b = 0x1.8p1;
double c = 0XAp-1;
~~~

The following forms are invalid:

~~~java
// Missing p/P exponent:
double a = 0x1.8;

// Using e/E instead of p/P:
double b = 0x1.8e1;
~~~

In base 16, the character `e` is also a valid digit with value 14. Java uses `p`/`P` to delimit the exponent part of a hex floating-point literal.

### 5.2. F and D Suffixes for Floating-Point Numbers

Hex floating-point literals default to `double`. You can append:

- `F` or `f`: `float` type.
- `D` or `d`: `double` type.

~~~java
double precise = 0x1.8p1;
double explicitDouble = 0x1.8p1D;
float singlePrecision = 0x1.8p1F;
~~~

Here `F`/`D` is a floating-point type suffix. Do not confuse this with `F` in an integer literal like `0x1F`: in that position, `F` is the hex digit 15.

### 5.3. Separators in Hex Floating-Point Literals

Underscores can also group digits in the significand and exponent, as long as they are between digits:

~~~java
double a = 0xA.B_Cp1_0;
float b = 0x1.8p1_0F;
~~~

Do not place underscores immediately after `0x`, adjacent to the decimal point, adjacent to `p`, or immediately before the suffix:

~~~java
// Invalid forms:
// double a = 0x_1.0p0;
// double b = 0x1._0p0;
// double c = 0x1.0_p0;
// double d = 0x1.0p_2;
// float e = 0x1.0p2_F;
~~~

## 6. Separators, Prefixes, and Suffixes: Reading a Literal in Order

When encountering a long literal, read it from left to right:

~~~java
long mask = 0x00FF_FF00_1234_ABCDL;
~~~

Breakdown:

1. `0x`: prefix indicating base 16.
2. `00FF`, `FF00`, `1234`, `ABCD`: groups of digits.
3. `_`: separator between groups, ignored when computing the value.
4. `L`: suffix specifying the `long` type.

Another example:

~~~java
float ratio = 0x1.8p1F;
~~~

Breakdown:

1. `0x`: base 16.
2. `1.8`: base-16 significand.
3. `p1`: multiply by 2 to the power 1.
4. `F`: `float` type suffix.

Not every hex literal has all three components. An integer literal can consist of just a prefix and digits; separators are optional, and the `L` suffix is only needed when you want `long` or need to clarify the type. Hex floating-point requires a `p`/`P` exponent.

## 7. Using Hex Numbers in Bit Masks and Bitwise Operations

Base 16 is particularly useful when representing bits because each hex digit corresponds to exactly 4 bits.

Example:

~~~java
int flags = 0x2D;
~~~

`0x2D` corresponds in binary to:

~~~text
2     D
0010  1101
~~~

Some common masks:

| Literal | Binary (4-bit groups) | Illustrative meaning |
|---|---|---|
| `0x0F` | `0000 1111` | Low 4 bits |
| `0xF0` | `1111 0000` | High 4 bits of a byte |
| `0xFF` | `1111 1111` | All 8 bits |
| `0xFF00` | `1111 1111 0000 0000` | Second byte in 16 bits |
| `0xFFFF_0000` | 16 one-bits, then 16 zero-bits | Upper half mask of an int |

Example extracting the low byte:

~~~java
int value = 0x12AB;
int lowByte = value & 0xFF;

System.out.printf("0x%02X%n", lowByte); // 0xAB
~~~

Example extracting the high byte in 16 bits:

~~~java
int highByte = (value >>> 8) & 0xFF;
System.out.printf("0x%02X%n", highByte); // 0x12
~~~

Separators make masks easier to read:

~~~java
int flags = 0b1010_0101;
int mask = 0xF0;
int upperNibble = flags & mask;
~~~

Here `0xF0` selects the high 4 bits of a byte. Hex notation keeps mask structure close to how engineers read binary data.

## 8. Distinguishing Base-16 Literals from Strings Containing Hex Numbers

A literal is written directly in source code:

~~~java
int value = 0xFF;
~~~

This differs from text data received from a file, network, or user:

~~~java
String input = "FF";
int value = Integer.parseInt(input, 16);
~~~

`Integer.parseInt(input, 16)` accepts hex digits **without the `0x` prefix**:

~~~java
int a = Integer.parseInt("FF", 16);   // 255
int b = Integer.parseInt("7f", 16);   // 127
~~~

If the string has a `0x` prefix, you can use `Integer.decode`:

~~~java
int a = Integer.decode("0xFF");
int b = Integer.decode("0X7f");
~~~

Do not confuse the two APIs:

~~~java
Integer.parseInt("0xFF", 16); // NumberFormatException
Integer.decode("0xFF");       // 255
~~~

For strings containing values exceeding the signed `int` range, distinguish the parsing intent:

~~~java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);

System.out.println(bits); // -1 when printed as a signed int
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
~~~

If you need integers of arbitrary magnitude, unrestricted by 32/64 bits, you can use `BigInteger`:

~~~java
import java.math.BigInteger;

BigInteger value = new BigInteger("FFFFFFFFFFFFFFFF", 16);
System.out.println(value); // 18446744073709551615
~~~

User input should be validated and handle `NumberFormatException` when the string is not a valid hex number.

## 9. Converting Numbers to Hexadecimal Strings

When you need to display a number in hex, you can use these methods:

~~~java
int value = 255;

String lower = Integer.toHexString(value);
String upper = Integer.toHexString(value).toUpperCase();

System.out.println(lower); // ff
System.out.println(upper); // FF
~~~

`toHexString` methods do not automatically add the `0x` prefix and do not add leading zeros.

To display a fixed width, use a Formatter:

~~~java
int value = 255;

System.out.println("0x%08X".formatted(value)); // 0x000000FF
System.out.println("0x%08x".formatted(value)); // 0x000000ff
~~~

| Format | Meaning |
|---|---|
| `%x` | Lowercase hex |
| `%X` | Uppercase hex |
| `%08X` | Minimum width 8 characters, left-padded with zeros |
| `0x%08X` | Explicitly adds the `0x` display prefix |

The width in Formatter is a **minimum width**, not a maximum limit. If the number needs more than 8 digits, Formatter still prints all of them.

For negative numbers, `Integer.toHexString(-1)` yields `ffffffff`, which is the 32-bit representation of `int -1`. If you want to represent an unsigned value, choose the appropriate unsigned API and be clear about the bit width to display.

## 10. Common Mistakes

| Mistake | Example | Explanation / Fix |
|---|---|---|
| Forgetting the prefix | `int x = FF;` | `FF` is not a literal; use `0xFF` |
| Wrong prefix | `int x = #FF;` | Java uses `0x` or `0X` |
| Misplaced separator | `0x_FF` | `_` must be between digits |
| Trailing separator | `0xFF_` | Do not end a literal with `_` |
| Separator adjacent to suffix | `0xFF_L` | Write `0xFFL` |
| Confusing l with digit 1 | `0xFFl` | Lowercase form can be valid but hard to read; prefer `0xFFL` |
| Thinking L makes a literal unsigned | `0xFFFF_FFFFL` | This is a signed `long` with value 4,294,967,295 |
| Thinking Java has a U suffix | `0xFFU` | Java does not support unsigned suffixes |
| Confusing F as a suffix in every case | `0x1F` | This is the integer literal 31; F is a hex digit |
| Forgetting p/P in hex float | `0x1.8` | Hex floating-point requires a `p`/`P` exponent |
| Using e/E for hex float exponent | `0x1.8e2` | Binary exponent uses `p`/`P` |
| Assigning large literal to byte/short without cast | `byte b = 0xFF;` | Literal is int 255, outside byte range; cast if keeping bits intentionally |
| Using parseInt with prefixed string | `Integer.parseInt("0xFF", 16)` | Use `Integer.decode("0xFF")` or strip the prefix before parsing |

## 11. Comprehensive Example Running on Java 17

Create file **`HexLiteralDemo.java`**:

~~~java
import java.math.BigInteger;

public class HexLiteralDemo {
    public static void main(String[] args) {
        // Prefix and digit separators.
        int color = 0xFF_33_66;
        int mask = 0x00FF_FF00;

        // L suffix for a long literal.
        long address = 0x0000_7FFF_FFFF_FFFFL;

        // Hex floating-point.
        double three = 0x1.8p1;
        float quarter = 0x1.0p-2F;

        // Signed int bit pattern and unsigned display.
        int allBits = 0xFFFF_FFFF;

        System.out.println(color); // 16724838
        System.out.printf("Mask: 0x%08X%n", mask);
        System.out.printf("Address: 0x%016X%n", address);
        System.out.println(three); // 3.0
        System.out.println(quarter); // 0.25
        System.out.println(allBits); // -1
        System.out.println(Integer.toUnsignedString(allBits)); // 4294967295

        // Parse a base-16 string.
        int parsed = Integer.parseInt("CAFE", 16);
        System.out.println(parsed); // 51966

        BigInteger large = new BigInteger("FFFFFFFFFFFFFFFF", 16);
        System.out.println(large); // 18446744073709551615
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 HexLiteralDemo.java
java HexLiteralDemo
~~~

This example uses official Java 17 syntax and does not require `--enable-preview`.

## 12. Process for Reading and Writing Base-16 Literals

When encountering a literal, analyze it in order:

~~~text
0x00FF_FF00_1234_ABCDL
| |              |  |
| |              |  +-- L suffix: long type
| |              +----- Last digit
| +-------------------- Separator between digit groups
+---------------------- 0x prefix: base 16
~~~

Then determine:

1. Is this an integer or floating-point literal?
2. Is the prefix `0x`/`0X`?
3. Are all `_` characters validly placed between digits?
4. Does the suffix specify the desired type?
5. If it is an integer literal, does the highest bit cause the value to be interpreted as negative under two's complement?
6. If it is a floating-point literal, does the exponent use `p`/`P`?
7. If the data arrives at runtime as a string, should you use `parseInt`, `decode`, `parseUnsignedInt`, or `BigInteger`?

## 13. Self-Practice Exercises

### Exercise 1: Reading Literal Values

Determine the decimal values of:

~~~java
int a = 0x2A;
int b = 0xFF;
int c = 0x10_00;
long d = 0x1_0000_0000L;
~~~

**Answers:**

- `a = 42`.
- `b = 255`.
- `c = 4096`.
- `d = 4,294,967,296`.

### Exercise 2: Classifying Valid Syntax

Consider the literals:

~~~java
0xCA_FE
0XDEAD_BEEF
0x_FF
0xFF_
0xFFL
0xFF_L
0x1.8p1
0x1.8e1
~~~

**Suggested answers:**

- Valid: `0xCA_FE`, `0XDEAD_BEEF`, `0xFFL`, `0x1.8p1`.
- Invalid: `0x_FF`, `0xFF_`, `0xFF_L`, `0x1.8e1`.

### Exercise 3: Why Is `0xFFFFFFFF` Equal to -1?

Explain based on 32-bit width.

**Answer:** `0xFFFFFFFF` has all 32 bits equal to 1. When interpreted as a signed `int` using two's complement, that bit pattern has the value `-1`. To obtain the corresponding unsigned value 4,294,967,295, use `Integer.toUnsignedString` or `Integer.toUnsignedLong`.

### Exercise 4: Choosing a Suffix

Write appropriate literals for:

- Value 255 of type `int`.
- Value 255 of type `long`.
- Value 4,294,967,295 of type `long`.
- Value 3.0 of type `double` using hex floating-point.
- Value 0.25 of type `float` using hex floating-point.

**Answers:**

~~~java
int a = 0xFF;
long b = 0xFFL;
long c = 0xFFFF_FFFFL;
double d = 0x1.8p1;
float e = 0x1.0p-2F;
~~~

### Exercise 5: Parsing a Hex String

Given `String input = "0xCAFE";`, convert it to an integer.

**Answer:**

~~~java
int value = Integer.decode(input);
~~~

Or strip the prefix first and call:

~~~java
int value = Integer.parseInt(input.substring(2), 16);
~~~

### Exercise 6: Byte Representation

Why does `byte value = 0xFF;` fail to compile, whereas `byte value = (byte) 0xFF;` is valid?

**Answer:** `0xFF` is an `int` literal with value 255, which exceeds the `byte` range of -128 to 127. The explicit cast preserves the low 8 bits; the pattern `11111111` is interpreted as `-1` for a signed byte.

## 14. References

- [Java Language Specification 17 — Integer Literals](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.1): integer literal syntax, prefixes, separators, suffixes, and type rules.
- [Java Language Specification 17 — Floating-Point Literals](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.2): decimal and hexadecimal floating-point literal syntax.
- [Oracle Java SE 17 — Primitive Data Types](https://docs.oracle.com/javase/tutorial/java/nutsandbolts/datatypes.html): bit widths and value ranges of primitive types.
- [Oracle Java SE 17 — Integer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): parsing, decoding, conversion, and unsigned operations for `int`.
- [Oracle Java SE 17 — Long API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): conversion methods and unsigned operations for `long`.
- [Oracle Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): representing and parsing arbitrary-precision integers.
