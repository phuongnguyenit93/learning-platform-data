# Formatting Integer Values with `toHexDigits` in Java 17

## 1. Lesson Objectives

Hexadecimal (base 16) is commonly used to represent bytes, bit masks, color codes, addresses, binary data, and integer values during debugging. In Java 17, the `java.util.HexFormat` class provides `toHexDigits` methods to convert primitive integer values directly into hexadecimal digit strings.

Example:

~~~java
import java.util.HexFormat;

HexFormat hex = HexFormat.of();

System.out.println(hex.toHexDigits((byte) 0x2A)); // 2a
System.out.println(hex.toHexDigits(0x2A));        // 0000002a
~~~

The two calls produce outputs of different lengths because the input types differ:

- `byte` has 8 bits, so its full representation requires 2 hex digits.
- `int` has 32 bits, so its full representation requires 8 hex digits.

`toHexDigits` does not convert a number to decimal, nor does it automatically add a `0x` prefix. It represents **the bits of an integer value in groups of four bits (nibbles)** as hex digits.

After this lesson, learners should be able to:

1. Use `HexFormat.of().toHexDigits(...)` for `byte`, `short`, `int`, and `long`.
2. Explain why the default output has a fixed width determined by the primitive type.
3. Understand the overload taking `digits` and the effect of keeping only a subset of hex digits.
4. Distinguish the two's complement bit representation of negative numbers from signed decimal integer representation.
5. Distinguish `toHexDigits`, `Integer.toHexString`/`Long.toHexString`, and `formatHex(byte[])`.
6. Choose the right formatting approach for binary data, verify results, and handle cases requiring round-tripping.

**Version scope:** `HexFormat` was introduced in Java 17; the examples here use standard Java SE 17 APIs and do not require enabling preview features.

## 2. Foundation: One Hex Digit Represents Four Bits

Hexadecimal has 16 symbols:

~~~text
Value:   0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15
Symbol:  0 1 2 3 4 5 6 7 8 9  A  B  C  D  E  F
~~~

Each hex digit represents exactly one **nibble** (4 bits). Two hex digits represent one byte (8 bits):

~~~text
Hex:      A     5
Binary: 1010  0101
       └─ 4 bits ─┘
~~~

Examples:

- `0x0F` is `0000 1111` (15 in decimal).
- `0x10` is `0001 0000` (16 in decimal).
- `0xFF` is `1111 1111` (255 when viewed as an unsigned byte).
- `0x1234` consists of four hex digits, corresponding to 16 bits.

In Java, primitive integer types are signed:

| Type | Width | Hex digits for full bit representation |
|---|---:|---:|
| `byte` | 8 bits | 2 |
| `short` | 16 bits | 4 |
| `int` | 32 bits | 8 |
| `long` | 64 bits | 16 |

The number of hex digits equals the bit width divided by 4. When formatting a primitive value, `HexFormat.toHexDigits` produces a string matching the type's width, even when a positive value could be written more concisely.

For example, the integer `10` could be written as `a` if only the shortest form were needed, but an `int` value has all 32 bits and is represented as `0000000a` by `toHexDigits(int)`.

## 3. The `java.util.HexFormat` API in Java 17

`HexFormat` is an immutable utility class for formatting and parsing hexadecimal data. Create an instance with:

~~~java
HexFormat hex = HexFormat.of();
~~~

The default instance uses lowercase hex digits. You can request uppercase:

~~~java
HexFormat upper = HexFormat.of().withUpperCase();
System.out.println(upper.toHexDigits(0x2A)); // 0000002A
~~~

`HexFormat` instances are immutable and thread-safe; you can create a preconfigured formatter and reuse it.

### 3.1. `toHexDigits` Overloads

Java 17 provides overloads for four integer types:

| Input type | Full-width format | Overload selecting digit count |
|---|---|---|
| `byte` | `toHexDigits(byte value)` | `toHexDigits(byte value, int digits)` |
| `short` | `toHexDigits(short value)` | `toHexDigits(short value, int digits)` |
| `int` | `toHexDigits(int value)` | `toHexDigits(int value, int digits)` |
| `long` | `toHexDigits(long value)` | `toHexDigits(long value, int digits)` |

The overloads without `digits` return a fixed number of digits based on the type width:

~~~java
HexFormat hex = HexFormat.of();

System.out.println(hex.toHexDigits((byte) 10));  // 0a
System.out.println(hex.toHexDigits((short) 10)); // 000a
System.out.println(hex.toHexDigits(10));         // 0000000a
System.out.println(hex.toHexDigits(10L));        // 000000000000000a
~~~

There is no need to manually prepend leading zeros; that is a built-in feature of the full-width representation.

### 3.2. No Dedicated Overloads for Every Type

`HexFormat.toHexDigits` does not provide overloads for `char`, `boolean`, `float`, `double`, or `BigInteger`. If you need to represent a value of those types, determine the intended semantics before converting:

- For `char`, you can format its code unit as a 16-bit integer.
- For `float`/`double`, if you want to inspect the IEEE 754 bit pattern, use bit-conversion APIs like `Float.floatToIntBits` or `Double.doubleToLongBits`, then format the resulting integer.
- For `BigInteger`, use its own API such as `toString(16)` when arbitrary-length representation is needed; handle sign and padding explicitly.

Do not arbitrarily cast a floating-point number to `int` and call `toHexDigits` if your goal is to inspect the floating-point bit pattern; arithmetic casting and bit conversion are two different operations.

## 4. Formatting According to Primitive Type Width

### 4.1. `byte`: Two Hex Digits

~~~java
HexFormat hex = HexFormat.of();

byte value = 42;
System.out.println(hex.toHexDigits(value)); // 2a
~~~

A `byte` value has 8 bits. One hex digit represents only 4 bits, so two digits are needed to represent the full byte.

Example with a bit pattern:

~~~java
byte data = (byte) 0xA5;
System.out.println(data);                    // -91 (signed byte)
System.out.println(hex.toHexDigits(data));   // a5
~~~

This is an essential point: the decimal value printed is `-91`, but the byte's bit pattern is `1010 0101`, which is written as `a5`. `toHexDigits` represents the bit pattern at the type's width and does not print a minus sign.

### 4.2. `short`: Four Hex Digits

~~~java
short value = (short) 0x1234;
System.out.println(hex.toHexDigits(value)); // 1234
~~~

With a negative value:

~~~java
short minusOne = -1;
System.out.println(hex.toHexDigits(minusOne)); // ffff
~~~

`short` is 16 bits; `-1` has an all-ones bit pattern in 16-bit two's complement representation.

### 4.3. `int`: Eight Hex Digits

~~~java
int value = 0x1234ABCD;
System.out.println(hex.toHexDigits(value)); // 1234abcd
~~~

With a small number:

~~~java
System.out.println(hex.toHexDigits(15)); // 0000000f
~~~

With a negative number:

~~~java
System.out.println(hex.toHexDigits(-1)); // ffffffff
~~~

The result `ffffffff` represents the 32 bits of `int -1`, not a string with a minus sign.

### 4.4. `long`: Sixteen Hex Digits

~~~java
long value = 0x0123456789ABCDEFL;
System.out.println(hex.toHexDigits(value)); // 0123456789abcdef
~~~

With `long -1L`:

~~~java
System.out.println(hex.toHexDigits(-1L)); // ffffffffffffffff
~~~

Fixed width makes bit patterns easy to compare and read, especially when working with 64-bit masks, binary IDs, or protocol data.

## 5. Meaning of Digit Count in `toHexDigits(value, digits)`

The overload taking `digits` lets you extract a specific number of hex digits from a value. The digit count must be between 1 and the maximum width of the type:

| Type | Valid `digits` values |
|---|---|
| `byte` | 1 to 2 |
| `short` | 1 to 4 |
| `int` | 1 to 8 |
| `long` | 1 to 16 |

If `digits` is smaller than the full width, the **higher hex digits are discarded**, keeping only the lowest digits.

Example:

~~~java
HexFormat hex = HexFormat.of();

int value = 0x12345678;
System.out.println(hex.toHexDigits(value));    // 12345678
System.out.println(hex.toHexDigits(value, 4)); // 5678
System.out.println(hex.toHexDigits(value, 2)); // 78
System.out.println(hex.toHexDigits(value, 1)); // 8
~~~

This is **high-order truncation**, not automatic rounding and not a check that the value fits in that many digits.

### 5.1. The `digits` Overload with Negative Values

~~~java
int value = -1;

System.out.println(hex.toHexDigits(value));    // ffffffff
System.out.println(hex.toHexDigits(value, 2)); // ff
~~~

Keeping the lowest two digits of the `int -1` bit pattern yields `ff`.

Similarly:

~~~java
System.out.println(hex.toHexDigits((byte) -1, 1)); // f
System.out.println(hex.toHexDigits((short) -1, 2)); // ff
~~~

Do not use the digit-truncating overload as a substitute for validation. For example, if an ID must be between 0 and 65535, calling `toHexDigits(id, 4)` with a larger `int` silently drops the high bits and may produce a string colliding with another ID. Validate the range before formatting.

### 5.2. Invalid `digits` Values

If `digits` is less than 1 or greater than the type's maximum digit count, the API throws `IllegalArgumentException`.

~~~java
hex.toHexDigits(10, 0); // IllegalArgumentException
hex.toHexDigits(10, 9); // IllegalArgumentException: int has at most 8 digits
~~~

Validate or fix `digits` from a verified configuration. Do not pass an arbitrary user-supplied digit count without checking it.

## 6. Digit Order and Two's Complement Representation

### 6.1. Digits Are Output from Highest to Lowest

Given the value:

~~~java
int value = 0x12345678;
~~~

The result `12345678` is ordered from the most significant nibble to the least significant nibble:

~~~text
int value:   0x12345678
Nibbles:     1 2 3 4 5 6 7 8
Significance: high          low
String:      "12345678"
~~~

This is the digit order of an integer value. It does not specify the byte order of a byte array in memory or a protocol. When converting an integer to a byte array, you must explicitly choose big-endian or little-endian.

### 6.2. Negative Numbers Are Not Written with a Minus Sign

Java signed integers are stored in fixed-width two's complement representation. Example:

~~~java
System.out.println(hex.toHexDigits((byte) -1));  // ff
System.out.println(hex.toHexDigits((short) -1)); // ffff
System.out.println(hex.toHexDigits(-1));         // ffffffff
System.out.println(hex.toHexDigits(-1L));        // ffffffffffffffff
~~~

The outputs have different digit counts because the data types have different bit widths. These are representations of the value's bits, not negative decimal strings like `-1`.

### 6.3. Zero-Padding for Positive Values and Zero

~~~java
System.out.println(hex.toHexDigits((byte) 1));  // 01
System.out.println(hex.toHexDigits((short) 1)); // 0001
System.out.println(hex.toHexDigits(1));         // 00000001
System.out.println(hex.toHexDigits(1L));        // 0000000000000001
~~~

Padding ensures every value of the same type has the same width. This is useful when reading binary dumps or comparing fixed-size fields.

## 7. Uppercase, Lowercase, and Prefixes

By default, `HexFormat.of()` uses lowercase digits a–f:

~~~java
HexFormat lower = HexFormat.of();
HexFormat upper = HexFormat.of().withUpperCase();

System.out.println(lower.toHexDigits(0xABCD)); // 0000abcd
System.out.println(upper.toHexDigits(0xABCD)); // 0000ABCD
~~~

You can inspect the configuration:

~~~java
System.out.println(lower.isUpperCase()); // false
System.out.println(upper.isUpperCase()); // true
~~~

### 7.1. `toHexDigits` Does Not Automatically Add `0x`

~~~java
String digits = hex.toHexDigits(0x2A);
System.out.println(digits);        // 0000002a
System.out.println("0x" + digits); // 0x0000002a
~~~

If a prefix is needed, prepend it explicitly or use the appropriate byte-array formatting API. Do not assume `withPrefix("0x")` changes the output of `toHexDigits`; prefix/delimiter/suffix are settings used for per-byte formatting in `formatHex`.

### 7.2. Creating Configured Formatters

~~~java
HexFormat upper = HexFormat.of().withUpperCase();
HexFormat colonSeparated = HexFormat.ofDelimiter(":");
~~~

`withUpperCase()`, `withDelimiter(...)`, `withPrefix(...)`, and `withSuffix(...)` return a configured formatter; they do not mutate the old instance. Delimiter/prefix/suffix options are primarily useful when formatting **byte arrays** with `formatHex`.

## 8. Distinguishing `toHexDigits`, `Integer.toHexString`, and `formatHex`

These three APIs are related but serve different purposes.

| API | Input | Output | Purpose |
|---|---|---|---|
| `HexFormat.toHexDigits(int)` | A primitive value | 8 hex digits | Full 32-bit representation of an `int` value |
| `Integer.toHexString(int)` | An `int` value | Unpadded hex string for positive values; 32-bit pattern for negative values | Compact hex conversion of an integer |
| `Long.toHexString(long)` | A `long` value | Compact hex form, or full bits for negative values | Hex conversion of a long integer |
| `HexFormat.formatHex(byte[])` | A byte sequence | Hex string of the bytes, optionally with delimiter/prefix/suffix | Representing binary data |

Example:

~~~java
int value = 42;

System.out.println(HexFormat.of().toHexDigits(value)); // 0000002a
System.out.println(Integer.toHexString(value));        // 2a
~~~

Both outputs describe the value 42 in base 16, but with different widths. Choose based on the output contract:

- If you need the full 32-bit representation: use `toHexDigits(int)`.
- If you need the shortest integer form: use `Integer.toHexString(int)`.
- If you need to convert a byte array to a hex string: use `formatHex(byte[])`.

### 8.1. Example with a Byte Array

~~~java
byte[] data = {0x01, 0x02, (byte) 0xAB};

HexFormat plain = HexFormat.of();
HexFormat separated = HexFormat.ofDelimiter(":").withUpperCase();

System.out.println(plain.formatHex(data));     // 0102ab
System.out.println(separated.formatHex(data)); // 01:02:AB
~~~

`formatHex` processes each byte in the array. It is not the same as `toHexDigits(int)`, which formats a single integer value according to its type width.

### 8.2. Per-Byte Prefix and Delimiter

~~~java
byte[] data = {0x01, 0x02, 0x0A};

HexFormat format = HexFormat.of()
        .withPrefix("0x")
        .withDelimiter(" ")
        .withUpperCase();

System.out.println(format.formatHex(data)); // 0x01 0x02 0x0A
~~~

In this string, the prefix is added to each byte. This is a useful convention for delimited byte dumps; do not confuse it with a single shared prefix for an integer formatted with `toHexDigits`.

## 9. Converting Integer Values to a Byte Array

`toHexDigits(int)` represents an integer value as a hex string in nibble order. If you need to represent **the bytes of an integer** for network transmission or file output, you must choose the byte order explicitly.

Example using `ByteBuffer`:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HexFormat;

int value = 0x12345678;

byte[] bigEndian = ByteBuffer.allocate(Integer.BYTES)
        .order(ByteOrder.BIG_ENDIAN)
        .putInt(value)
        .array();

byte[] littleEndian = ByteBuffer.allocate(Integer.BYTES)
        .order(ByteOrder.LITTLE_ENDIAN)
        .putInt(value)
        .array();

HexFormat hex = HexFormat.of();
System.out.println(hex.formatHex(bigEndian));   // 12345678
System.out.println(hex.formatHex(littleEndian)); // 78563412
~~~

The two byte arrays have different byte orders, even though they represent the same `int` value. `toHexDigits(value)` produces the digit string `12345678` without deciding protocol byte order.

When working with binary protocols, file formats, or hardware, follow the specification's endianness. Do not infer byte order merely from the fact that an integer's hex string prints left to right.

## 10. Round-Trip: Formatting and Parsing Back

For an integer primitive, `toHexDigits` only formats to a string; there is no corresponding `parseHexDigits` method on `HexFormat` for primitives. Choose the parsing API appropriate for the type.

### 10.1. Parsing `int` and `long`

~~~java
int value = 0x1234ABCD;
String digits = HexFormat.of().toHexDigits(value);

int parsed = Integer.parseUnsignedInt(digits, 16);
System.out.println(parsed == value); // true
~~~

Why use `parseUnsignedInt`? The `toHexDigits(int)` string may start with a high hex digit from `8` to `f`, in which case the 32-bit value interpreted as an unsigned bit pattern exceeds `Integer.MAX_VALUE`. `parseUnsignedInt` reads all 32 bits and returns the exact same bit pattern in a signed `int`.

For `long`:

~~~java
long value = 0xFEDCBA9876543210L;
String digits = HexFormat.of().toHexDigits(value);

long parsed = Long.parseUnsignedLong(digits, 16);
System.out.println(parsed == value); // true
~~~

Unsigned parsing methods do not turn `int` or `long` into new unsigned types; they allow parsing the full bit range and storing the result in a signed primitive.

### 10.2. Parsing `byte` and `short`

`Byte.parseByte` and `Short.parseShort` accept signed values within the type's range. If a hex string represents a bit pattern with the highest bit set to 1, its unsigned value exceeds the positive range of the type, so you must parse via a wider type or handle the byte pattern:

~~~java
byte original = (byte) 0xA5;
String digits = HexFormat.of().toHexDigits(original);

int parsedBits = Integer.parseInt(digits, 16);
byte restored = (byte) parsedBits;

System.out.println(digits);               // a5
System.out.println(restored == original); // true
~~~

Here `Integer.parseInt("a5", 16)` returns 165; casting to `byte` keeps the low 8 bits, reproducing the original bit pattern.

For `short`, a similar approach applies:

~~~java
short original = (short) 0xF234;
String digits = HexFormat.of().toHexDigits(original);

short restored = (short) Integer.parseInt(digits, 16);
System.out.println(restored == original); // true
~~~

Only perform the cast after controlling the hex string and digit count; do not use this technique to accept arbitrary input while skipping validation.

### 10.3. Parsing Byte Arrays with `HexFormat.parseHex`

`formatHex(byte[])` has a matching parse method:

~~~java
HexFormat hex = HexFormat.of();
byte[] bytes = {(byte) 0x80, 0x01, 0x2A};

String encoded = hex.formatHex(bytes);
byte[] decoded = hex.parseHex(encoded);

System.out.println(encoded); // 80012a
System.out.println(java.util.Arrays.equals(bytes, decoded)); // true
~~~

If a delimiter, prefix, or suffix was configured, use the matching formatter to parse the string according to that format. Do not assume strings with arbitrary separators can be parsed by the default formatter.

## 11. Validating Data Before Formatting

### 11.1. Full-Width Formatting Does Not Validate Business Rules

`toHexDigits(int)` accepts any `int` value, including negative numbers. If a business field only permits non-negative numbers, validate it first:

~~~java
static String formatId(int id) {
    if (id < 0) {
        throw new IllegalArgumentException("id must be non-negative");
    }
    return HexFormat.of().toHexDigits(id);
}
~~~

Do not rely on digit count to infer data validity.

### 11.2. Truncating Digits Can Lose Information

~~~java
int first = 0x12345678;
int second = 0xABCDEF78;

String a = HexFormat.of().toHexDigits(first, 2);  // 78
String b = HexFormat.of().toHexDigits(second, 2); // 78
~~~

Two different values produce the same output because only the lowest two digits are kept. This is why you should not use the `digits` overload to format unique identifiers without range validation.

### 11.3. Do Not Mix Up Signed and Unsigned Bytes

Java `byte` has the range `-128..127`, whereas bytes in protocols are often interpreted as unsigned values `0..255`. `toHexDigits(byte)` represents all 8 bits directly, without needing an unsigned conversion first:

~~~java
byte raw = (byte) 0xFE;
System.out.println(raw); // -2
System.out.println(HexFormat.of().toHexDigits(raw)); // fe
System.out.println(Byte.toUnsignedInt(raw)); // 254
~~~

When you need an unsigned integer for arithmetic, use `Byte.toUnsignedInt(raw)`; when you need to represent a byte as two hex digits, use `toHexDigits(raw)`.

## 12. Comprehensive Example Running on Java 17

The program below formats integer types and demonstrates negative numbers, uppercase, digit truncation, and byte-order conversion:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HexFormat;

public class Main {
    public static void main(String[] args) {
        HexFormat lower = HexFormat.of();
        HexFormat upper = HexFormat.of().withUpperCase();

        byte byteValue = (byte) 0xA5;
        short shortValue = (short) 0x1234;
        int intValue = 0x12345678;
        long longValue = 0x0123456789ABCDEFL;

        System.out.println(lower.toHexDigits(byteValue));  // a5
        System.out.println(lower.toHexDigits(shortValue)); // 1234
        System.out.println(lower.toHexDigits(intValue));   // 12345678
        System.out.println(lower.toHexDigits(longValue));  // 0123456789abcdef

        System.out.println(upper.toHexDigits(0xABCDEF));   // 00ABCDEF
        System.out.println(lower.toHexDigits(0x12345678, 4)); // 5678
        System.out.println(lower.toHexDigits(-1));         // ffffffff

        byte[] bytes = ByteBuffer.allocate(Integer.BYTES)
                .order(ByteOrder.BIG_ENDIAN)
                .putInt(intValue)
                .array();
        System.out.println(lower.formatHex(bytes));        // 12345678
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 -encoding UTF-8 Main.java
java Main
~~~

Sample output:

~~~text
a5
1234
12345678
0123456789abcdef
00ABCDEF
5678
ffffffff
12345678
~~~

Note: `0xABCDEF` has six significant hex digits, but the `int` type requires a full eight digits, so the output has two leading zeros: `00ABCDEF`. Use this example to see that uppercase configuration only changes `a..f` to `A..F`, not the width.

## 13. Common Mistakes

### 13.1. Expecting No Leading Zeros

~~~java
HexFormat.of().toHexDigits(10); // 0000000a
~~~

This is the expected result: the `int` overload returns all eight digits. If you want the shortest form, use `Integer.toHexString(10)` or format according to another contract.

### 13.2. Thinking Negative Numbers Get a Minus Sign

~~~java
HexFormat.of().toHexDigits(-1); // ffffffff
~~~

This is the 32-bit pattern of `int -1`, not the string `-1`.

### 13.3. Using `digits` to Request Extra Padding

`toHexDigits(value, digits)` is not a way to request an arbitrary length larger than the type width. `digits` must be within the allowed range, and when it is smaller than the type width, the high nibbles are discarded.

### 13.4. Confusing `toHexDigits(int)` with Formatting a Byte

~~~java
int value = 0xA5;
System.out.println(HexFormat.of().toHexDigits(value));    // 000000a5
System.out.println(HexFormat.of().toHexDigits(value, 2)); // a5
System.out.println(HexFormat.of().toHexDigits((byte) value)); // a5
~~~

Choose the input type that matches the actual data field width.

### 13.5. Thinking `withPrefix` Applies to `toHexDigits`

Prefix, delimiter, and suffix are used when formatting byte arrays with `formatHex`. `toHexDigits` returns the digit string for a single primitive. If `0x` is needed, prepend it explicitly:

~~~java
String display = "0x" + HexFormat.of().toHexDigits(42);
~~~

### 13.6. Confusing Digit Order with Endianness

`toHexDigits(0x12345678)` returns `12345678`; when converting the value to a little-endian byte array, `formatHex` can return `78563412`. Determine byte order from the data specification, not from the method name.

### 13.7. Using with Floating-Point Numbers Without Bit Conversion

`toHexDigits` has no `double` overload. If you want to inspect the bit pattern of a `double`, use `Double.doubleToLongBits(value)` or `Double.doubleToRawLongBits(value)` depending on whether raw NaN payloads need to be preserved, then format the `long`. Casting a `double` directly to `long` is a numeric value conversion, not a bit-pattern view.

## 14. Practice Exercises

### Exercise 1 — Width by Type

Predict the output:

~~~java
HexFormat hex = HexFormat.of();
System.out.println(hex.toHexDigits((byte) 1));
System.out.println(hex.toHexDigits((short) 1));
System.out.println(hex.toHexDigits(1));
System.out.println(hex.toHexDigits(1L));
~~~

**Answer:**

~~~text
01
0001
00000001
0000000000000001
~~~

Explain based on 8-, 16-, 32-, and 64-bit widths.

### Exercise 2 — Selecting Low Digits

Given `int value = 0xCAFEBABE`, call `toHexDigits(value, 4)`.

**Answer:** `babe`; the four high digits `cafe` are discarded.

### Exercise 3 — Negative Numbers

Predict:

~~~java
hex.toHexDigits((byte) -1)
hex.toHexDigits((short) -1)
hex.toHexDigits(-1)
hex.toHexDigits(-1L)
~~~

**Answer:** `ff`, `ffff`, `ffffffff`, `ffffffffffffffff`. Each output shows the two's complement bit pattern at the type's width.

### Exercise 4 — Uppercase and Prefix

Create an uppercase formatter, format `0x00ABCDEF`, and build a string with the `0x` prefix.

~~~java
HexFormat upper = HexFormat.of().withUpperCase();
String result = "0x" + upper.toHexDigits(0x00ABCDEF);
System.out.println(result); // 0x00ABCDEF
~~~

### Exercise 5 — Distinguishing Integers and Byte Arrays

Given `int value = 0x12345678`, format the value with `toHexDigits`, then convert it into four big-endian bytes and format with `formatHex`. Explain why the two strings match under big-endian, but differ when the byte order is little-endian.

### Exercise 6 — Round-Trip

Format an arbitrary `int` with `toHexDigits`, parse it back with `Integer.parseUnsignedInt(text, 16)`, and verify `==` against the original value. Test negative numbers as well to understand why unsigned parsing is needed.

## 15. Completion Criteria

Learners have mastered this lesson when they can:

1. Explain that one hex digit represents 4 bits and two hex digits represent one byte.
2. Call the appropriate `HexFormat.toHexDigits` overload for `byte`, `short`, `int`, and `long`.
3. Predict the default lengths: 2, 4, 8, and 16 digits.
4. Explain that negative numbers are represented as two's complement bit patterns without a minus sign.
5. Use `digits` within the valid range and recognize that choosing fewer digits discards the high nibbles.
6. Choose lowercase/uppercase and understand that `toHexDigits` does not add prefixes automatically.
7. Distinguish `toHexDigits`, `Integer.toHexString`, and `formatHex(byte[])`.
8. Distinguish hex digit order from the byte order of binary data.
9. Format and parse integer values / byte arrays back using appropriate parsing APIs and range checks.
10. Compile examples with JDK 17 without preview flags.

## 16. Official Documentation

- [Java SE 17 API — `HexFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): `toHexDigits`, `formatHex`, and `parseHex` overloads, plus uppercase, prefix, delimiter, and suffix settings.
- [Java SE 17 API — `Integer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `toHexString`, `parseUnsignedInt`, and integer conversions.
- [Java SE 17 API — `Long`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): `toHexString` and `parseUnsignedLong`.
- [Java SE 17 API — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): converting integers to byte arrays with a specified byte order.

**Takeaway:** `toHexDigits` formats an integer's bit pattern at the primitive's full width: 2/4/8/16 digits for byte/short/int/long. The `digits` overload keeps only the low digits and can discard information. Use `formatHex` for byte arrays, `toHexString` for compact integer hex strings, and always define byte order explicitly when data is exchanged as bytes.
