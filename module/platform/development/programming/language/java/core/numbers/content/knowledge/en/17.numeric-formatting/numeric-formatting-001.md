# `Integer.toString`, `Long.toString`, and `radix` in Java

Java stores `int` and `long` values as signed binary integers. When a program needs to display them on screen, write logs, exchange data, or output text in base 2, 8, 10, 16, etc., we must **format the numeric value into a `String`**. `Integer.toString` and `Long.toString` are the two fundamental APIs that perform this task.

```java
int number = 42;

System.out.println(Integer.toString(number));      // 42
System.out.println(Integer.toString(number, 2));   // 101010
System.out.println(Integer.toString(number, 8));   // 52
System.out.println(Integer.toString(number, 16));  // 2a
```

All four results are **different strings representing the same integer value 42**. The `radix` parameter determines **the base when converting into digits**, does not modify the variable's original value, and does not add prefixes such as `0x`. For negative numbers, there is also an important distinction between formatting a **signed value** with `toString(value, radix)` and formatting an **unsigned bit pattern** with `toHexString`, `toBinaryString`, or `toUnsignedString`.

This lesson focuses on the contract of both methods, valid radices, negative/positive and boundary values, their relationship with parsers, ways to format with prefixes/width, and common mistakes when storing or transmitting numbers.

## 1. Numeric values differ from how numbers are written

Suppose a program has:

```java
int a = 42;
int b = 0x2A;
int c = 0b101010;
int d = 052;
```

In Java source code, the compiler interprets four **integer literals** in base 10, 16, 2, and 8. However, all variables here hold the arithmetic value **42**. An `int` variable **retains no memory** of whether it was assigned using a hex or binary literal.

`Integer.toString(a, 16)`, `Integer.toString(b, 16)`, `Integer.toString(c, 16)`, and `Integer.toString(d, 16)` all return `"2a"`. The method does not recover the original literal syntax: it receives the **value**, then builds the digit string in the requested base.

### Concepts to distinguish

| Concept | Example | Stage and effect |
| --- | --- | --- |
| Numeric literal | `0x2A`, `0b101010`, `42` | Source code syntax, parsed by the compiler |
| Primitive numeric value | `int value = 42;` | Arithmetic value manipulated at runtime |
| Numeric formatting | `Integer.toString(value, 16)` | Creates a `String` representing the value in base 16 |
| Numeric parsing | `Integer.parseInt("2a", 16)` | Reads a `String` according to a base and produces an `int` value |
| Unsigned bit formatting | `Integer.toHexString(-1)` | Interprets the 32-bit pattern as unsigned |

**Formatting and parsing are two opposite directions.** Do not use `parseInt` when the goal is to *display* a number; nor use `toString` to *validate* an input string.

## 2. Important overloads

`Integer` and `Long` reside in `java.lang`, so no separate import is needed.

| API | Parameters | Return type | Meaning |
| --- | --- | --- | --- |
| `Integer.toString(int value)` | One `int` | `String` | Signed decimal representation |
| `Integer.toString(int value, int radix)` | Value and base | `String` | Signed representation in the requested base |
| `Long.toString(long value)` | One `long` | `String` | Signed decimal representation |
| `Long.toString(long value, int radix)` | Value and base | `String` | Signed representation in the requested base |

```java
int count = -42;
long distance = 4_294_967_296L;

String a = Integer.toString(count);       // "-42"
String b = Integer.toString(count, 16);   // "-2a"
String c = Long.toString(distance);       // "4294967296"
String d = Long.toString(distance, 16);   // "100000000"
```

Distinguish the class names by data type: `Long.toString` accepts `long` and handles a wider range than `int`. You **cannot** expect calling `Integer.toString((int) someLong)` to preserve a `long` value that exceeds the `int` range, because information can be lost in the **cast before the call**.

The methods above are `static`: use `Integer.toString(...)` or `Long.toString(...)`. There is no need to create `new Integer(...)`/`new Long(...)` for formatting.

### What about `String.valueOf` and string concatenation?

`String.valueOf(42)`, `Integer.toString(42)`, and `"" + 42` normally produce the base-10 string `"42"`. However:

- `String.valueOf(int)`/`String.valueOf(long)` do not have a `radix` parameter.
- `Integer.toString(value, radix)` clearly expresses the intent to choose another base.
- `Integer.valueOf(int)` **creates/retrieves an `Integer` wrapper object**, not a string.
- `Integer.toString()` called on a **wrapper object** is a no-arg instance method, whereas `Integer.toString(int)` is a static method. Do not confuse the signatures.

In code that aims to explicitly display binary/hex, choose `toString(value, radix)` or a specialized API matching the signed/unsigned semantics.

## 3. `radix`: base 2 to 36

`radix` is the base used to express a number with digits. For the radix-accepting overloads of `Integer.toString` and `Long.toString`, valid values are:

```java
Character.MIN_RADIX // 2
Character.MAX_RADIX // 36
```

Java uses the digit characters:

```text
0 1 2 3 4 5 6 7 8 9 a b c ... z
```

- For radix 2: `0`, `1`.
- For radix 8: `0` through `7`.
- For radix 10: `0` through `9`.
- For radix 16: `0` through `9` and `a` through `f`.
- For radix 36: `0` through `9` and `a` through `z`.

The letters in the strings produced by both methods are **lowercase** (`a..z`).

```java
System.out.println(Integer.toString(42, 2));   // 101010
System.out.println(Integer.toString(42, 8));   // 52
System.out.println(Integer.toString(42, 10));  // 42
System.out.println(Integer.toString(42, 16));  // 2a
System.out.println(Integer.toString(35, 36));  // z
```

**There is no radix 1, 0, 37, or -2** in this API. One non-obvious point: `toString(value, radix)` **does not throw `NumberFormatException` when radix is outside 2–36**; instead, it **uses decimal (radix 10)** per the JDK contract.

```java
System.out.println(Integer.toString(255, 1));  // 255, fallback to radix 10
System.out.println(Long.toString(255L, 37));   // 255, fallback to radix 10
```

Because an invalid base can be masked, an application that receives `radix` from a user should **validate the range itself**:

```java
static String formatStrictRadix(int value, int radix) {
    if (radix < Character.MIN_RADIX || radix > Character.MAX_RADIX) {
        throw new IllegalArgumentException("radix must be from 2 to 36");
    }
    return Integer.toString(value, radix);
}
```

This is an illustrative method to be placed inside a class. It establishes a policy of **explicitly reporting an error when radix is invalid**, stricter than the decimal fallback choice of `Integer.toString`.

### `radix` does not alter the number

An integer `42` remains `42` whether displayed as `101010`, `52`, or `2a`. Only the resulting string differs. To convert the string back to the value, the parser must know the corresponding base:

```java
int original = 42;
String encoded = Integer.toString(original, 16);  // "2a"
int decoded = Integer.parseInt(encoded, 16);      // 42
```

If `Integer.parseInt("2a")` is called without radix 16, it will throw `NumberFormatException` because the parser defaults to decimal and the character `a` is invalid in radix 10.

## 4. Zero, positive, and negative cases

### Zero

```java
System.out.println(Integer.toString(0));       // "0"
System.out.println(Integer.toString(0, 2));    // "0"
System.out.println(Long.toString(0L, 36));     // "0"
```

The number 0 always has the string representation `"0"` in valid radices; there is no empty string or minus sign.

### Negative numbers: `-` sign precedes the digits

```java
System.out.println(Integer.toString(-42));      // -42
System.out.println(Integer.toString(-42, 2));   // -101010
System.out.println(Integer.toString(-42, 16));  // -2a
System.out.println(Long.toString(-42L, 36));    // -16
```

`Integer.toString(-42, 16)` returns **`"-2a"`**, not the 32-bit pattern string of the negative number. The digits `2a` represent the **magnitude 42**, while `-` conveys the sign. Therefore, these two strings:

- `Integer.toString(-1, 16)` → `"-1"`;
- `Integer.toHexString(-1)` → `"ffffffff"`;

both relate to the same `int -1` value but **follow different display conventions**.

### Is the boundary value `MIN_VALUE` handled properly?

```java
System.out.println(Integer.toString(Integer.MIN_VALUE));
// -2147483648
System.out.println(Long.toString(Long.MIN_VALUE));
// -9223372036854775808
```

`Integer.MIN_VALUE` equals `-2^31`, and `Long.MIN_VALUE` equals `-2^63`. The corresponding positive values cannot be represented in the same signed types. The JDK `toString` methods **handle both of these values correctly**. Do not implement a formatter yourself by taking `Math.abs(value)` first and converting bases while forgetting overflow:

```java
System.out.println(Math.abs(Integer.MIN_VALUE));
// -2147483648: still negative due to overflow.
```

If you need to implement a digit-conversion algorithm yourself, you must handle `MIN_VALUE` with safe techniques such as working on negative values or widening the type first. For normal application needs, using the built-in JDK methods is simpler.

## 5. Comparing signed formatting with bit-pattern representation

`Integer.toString(value, radix)` and `Long.toString(value, radix)` convert a **signed value** into digits in the chosen base. For negative numbers, they place a minus sign before the magnitude: `Integer.toString(-42,16)` is `"-2a"`. Meanwhile, `Integer.toHexString(-42)` is `"ffffffd6"`: it interprets the **unsigned 32-bit pattern** of the same variable.

```java
System.out.println(Integer.toString(-1,16)); // -1
System.out.println(Integer.toHexString(-1)); // ffffffff
System.out.println(Long.toString(-1L,16));   // -1
```

Do not use these two string styles interchangeably when a round-trip is required. Choose `toString(value, radix)` for signed values; choose the `toBinaryString`/`toHexString` group and `toUnsignedString` when you genuinely need to view the bit pattern. Sign extension rules, full-width 32/64-bit display, `parseUnsignedInt`/`parseUnsignedLong`, and `byte`/`short` limitations are the focus of the next lesson.

## 6. Unsigned representation is a separate contract

For `int -1`, `Integer.toUnsignedString(-1)` returns `"4294967295"`; with radix 16, `Integer.toUnsignedString(-1,16)` returns `"ffffffff"`. The bit pattern remains unchanged; only the way it is read changes. `Integer.parseUnsignedInt("ffffffff",16)` returns the same bit pattern, which if printed as a signed `int` will show `-1`.

```java
String text = Integer.toUnsignedString(-1, 16);
int decodedBits = Integer.parseUnsignedInt(text, 16);
System.out.println(decodedBits == -1); // true
```

Do not pass an unsigned string whose value is greater than `Integer.MAX_VALUE` into `Integer.parseInt` as signed. At API boundaries, clearly specify signedness, radix, and bit width. The lesson on `toBinaryString`, `toHexString`, and `toUnsignedString` covers these rules in depth.

## 7. Formatting does not automatically add `0x`, `0b`, `#`, or suffixes

`Integer.toString(42,16)` returns `"2a"`, not `"0x2a"`. `Long.toString(42L,2)` returns `"101010"` without `"0b"`. The formatter also **does not automatically add** grouping underscores, the letter `L`, uppercase letters, the `#` symbol, or a fixed width.

```java
String digits = Integer.toString(42, 16); // "2a"
String shown = "0x" + digits;             // "0x2a"
```

If the output string is for a **machine-to-machine protocol**, avoid adding decorative prefixes when the protocol only requires digits. If it is for UI or logs, prefixes can help readers identify the radix.

### Placing the minus sign and prefix in the right positions

A naive approach:

```java
String wrong = "0x" + Integer.toString(-42,16);
// "0x-2a" — not a standard syntax accepted by Integer.decode.
```

If you are designing a signed hex format compatible with `Integer.decode`, place the sign **before** the prefix:

```java
static String signedHexWithPrefix(int value) {
    String digits = Integer.toString(value, 16);
    if (digits.startsWith("-")) {
        return "-0x" + digits.substring(1);
    }
    return "0x" + digits;
}
```

```java
System.out.println(signedHexWithPrefix(-42)); // -0x2a
System.out.println(Integer.decode("-0x2a"));  // -42
```

This is an illustrative method to be placed inside a class. Using `substring(1)` on the existing sign avoids having to compute `-value`, because `-Integer.MIN_VALUE` can overflow. However, it applies to **signed values**, not unsigned bitmask conventions. For bitmasks, `"0x" + Integer.toHexString(value)` usually expresses the intent better.

## 8. Uppercase letters, leading zeros, and fixed width

The results of `toString(value,radix)` are minimal: no leading zeros are added, and lowercase letters are used. If a format requires **at least 8 hex digits**, you must apply a separate rule.

```java
int value = 42;
String padded = String.format(java.util.Locale.ROOT, "%08x", value);
System.out.println(padded); // 0000002a
```

`String.format` uses `Formatter` rules, where:

- `%x`: lowercase hexadecimal format.
- `%X`: uppercase hexadecimal format.
- `8`: minimum width of 8 characters.
- `0`: pads with leading zeros on the left to reach the width.
- `Locale.ROOT`: a stable choice for locale-independent formatting.

```java
System.out.println(String.format(java.util.Locale.ROOT,"%08X", 42));
// 0000002A
```

**Pitfall:** `%08x` does not mean "truncate to 8 characters". The width is a **minimum**, not a maximum limit. If a value requires more digits, the formatter does not automatically drop significant digits.

Additionally, for **negative integers** and `%x`, Formatter conventions may use the unsigned bit-pattern representation. Do not confuse it with `Integer.toString(-42,16)` producing `"-2a"`.

### What if you want exact 8 hex digits for an `int`?

`Integer.toHexString(value)` produces up to 8 hex digits for a 32-bit pattern, though it usually does not pad small numbers. You can use `String.format("%08x", value)` when you want to display the full 32-bit word. For `long`, `%016x` is commonly used to display the 16 hex digits of a 64-bit word.

### Do not lose leading zeros of identifier data

A string like `"00042"` might be a record code, not merely the arithmetic representation of 42. Converting it via:

```java
int n = Integer.parseInt("00042");
String restored = Integer.toString(n); // "42", lost the three leading zeros.
```

There is no way for `Integer.toString` to infer the original string width because the `int` variable **does not store** leading zeros. If you need to preserve the exact identifier, keep it as a `String` and validate against a schema. If fixed width is a business property, reformat it with the known width.

## 9. Parsing and formatting can be reversible, under conditions

With a valid radix `2..36` and an `int` value, the following pair restores the original value:

```java
int original = -42;
int radix = 16;
String text = Integer.toString(original, radix);
int restored = Integer.parseInt(text, radix);

System.out.println(text);                // -2a
System.out.println(restored == original); // true
```

Similarly for `long`:

```java
long original = 4_294_967_296L;
String text = Long.toString(original, 16); // "100000000"
long restored = Long.parseLong(text, 16);
```

The pairs are `toString`/`parseInt` and `Long.toString`/`Long.parseLong`; they do **not** automatically add `0x` or grouping characters. If you want to format an unsigned bit pattern, you must use the appropriate unsigned pair.

### What breaks a round trip

| Cause | Example | Result |
| --- | --- | --- |
| Parsing with the wrong radix | Format `42` radix 16 → `"2a"`, parse radix 10 | `NumberFormatException` |
| Adding a prefix then calling `parseInt` | `"0x2a"` with radix 16 | Parser does not automatically strip `0x` |
| Mixing unsigned bitstrings with a signed parser | `"ffffffff"` → `parseInt(...,16)` | Exceeds signed `int` range |
| Using a narrowing cast before formatting | `(int) 4_294_967_296L` | Value lost before `toString` runs |
| Dropping the sign symbol | Changing `"-2a"` to `"2a"` | Negative value turns into positive |
| Using an out-of-range radix without validation | `toString(255,1)` | Silent fallback to `"255"` in base 10 |
| Assuming formatting preserves whitespace/leading zeros | `"00042"` → parse → `toString` | Only `"42"` remains |

An integer protocol should **specify radix, signedness, prefix, letter case, width, leading-zero rules, and value range**. A single formatter method cannot replace a format specification.

## 10. Notes on Unicode digits and letter case

`Integer.toString(value, radix)` and `Long.toString(value, radix)` use an ASCII digit table of the form `0..9a..z`, suitable for locale-independent protocols.

Meanwhile, `Integer.parseInt(text, radix)` and `Long.parseLong(text, radix)` use digit rules based on `Character.digit`, so they can accept some JDK-supported Unicode digit characters, as well as uppercase `A..Z` for appropriate radices. **The canonical formatter output language and the input set accepted by the parser are not necessarily identical.**

```java
System.out.println(Integer.toString(255,16)); // ff
System.out.println(Integer.parseInt("FF",16)); // 255
System.out.println(Integer.parseInt("ff",16)); // 255
```

If a protocol mandates **ASCII-only, lowercase-only**, do not assume `parseInt` acts as a validator for the entire schema. Validate the character set and normalize according to the protocol's policy.

Using standard `toString` **does not depend on `Locale`** to select digit characters. If you need to display numbers according to cultural conventions such as thousands grouping or local decimal separators, use `NumberFormat`/`Formatter` appropriately. `Integer.toString` is advantageous when simple, consistent machine-to-machine strings are needed.

## 11. `Long.MIN_VALUE` and ranges larger than `int`

`long` is a 64-bit signed integer with a range from `-9_223_372_036_854_775_808` to `9_223_372_036_854_775_807`. When a value exceeds `int`, choose `Long.toString` to preserve the value.

```java
long large = 4_294_967_296L; // 2^32
System.out.println(Long.toString(large));    // 4294967296
System.out.println(Long.toString(large,16)); // 100000000
```

`Integer.toString` does not accept `long` directly without type conversion:

```java
// Integer.toString(large); // Compile error: long does not automatically narrow to int.
String wrong = Integer.toString((int) large); // "0": high bits lost.
```

For `Long.MIN_VALUE`, `Long.toString` guarantees returning the correct signed string `"-9223372036854775808"`. Just like with `int`, do not apply `Math.abs(Long.MIN_VALUE)` expecting a positive number of the same type, because `Math.abs(Long.MIN_VALUE)` remains negative due to overflow.

For integers even larger than `long`, choose `java.math.BigInteger`. `BigInteger.toString(int radix)` also supports representations in bases 2..36, but it has its own contract; do not force it into `longValue()` just to use `Long.toString`, as doing so can lose information.

## 12. Standalone Java 17+ program

Create the file `RadixFormatDemo.java`:

```java
import java.util.Locale;

public class RadixFormatDemo {
    public static void main(String[] args) {
        int n = -42;
        long large = 4_294_967_296L;

        System.out.println("Integer default: " + Integer.toString(n));
        System.out.println("Long default: " + Long.toString(large));
        System.out.println("42 base 2: " + Integer.toString(42, 2));
        System.out.println("42 base 8: " + Integer.toString(42, 8));
        System.out.println("42 base 16: " + Integer.toString(42, 16));
        System.out.println("-42 base 16: " + Integer.toString(-42, 16));
        System.out.println("35 base 36: " + Integer.toString(35, 36));
        System.out.println("255 base 16: " + Integer.toString(255, 16));
        System.out.println("255 invalid radix 1: "
                + Integer.toString(255, 1));
        System.out.println("long 4294967296 base 16: "
                + Long.toString(large, 16));

        System.out.println("int -1 toHexString: "
                + Integer.toHexString(-1));
        System.out.println("int -1 toString base 16: "
                + Integer.toString(-1, 16));
        System.out.println("unsigned -1 base 10: "
                + Integer.toUnsignedString(-1));
        System.out.println("unsigned -1 base 16: "
                + Integer.toUnsignedString(-1, 16));
        System.out.println("unsigned long -1 base 16: "
                + Long.toUnsignedString(-1L, 16));

        System.out.println("zero base 36: " + Long.toString(0L, 36));
        System.out.println("Integer.MIN_VALUE base 10: "
                + Integer.toString(Integer.MIN_VALUE));
        System.out.println("Long.MIN_VALUE base 10: "
                + Long.toString(Long.MIN_VALUE));

        System.out.println("Signed parse radix 16: "
                + Integer.parseInt(Integer.toString(-42, 16), 16));
        System.out.println("Unsigned parse hex: "
                + Integer.parseUnsignedInt(
                        Integer.toUnsignedString(-1, 16), 16));
        System.out.println("Padded hex: "
                + String.format(Locale.ROOT, "%08x", 42));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac --release 17 RadixFormatDemo.java
java RadixFormatDemo
```

Verified stdout:

```text
Integer default: -42
Long default: 4294967296
42 base 2: 101010
42 base 8: 52
42 base 16: 2a
-42 base 16: -2a
35 base 36: z
255 base 16: ff
255 invalid radix 1: 255
long 4294967296 base 16: 100000000
int -1 toHexString: ffffffff
int -1 toString base 16: -1
unsigned -1 base 10: 4294967295
unsigned -1 base 16: ffffffff
unsigned long -1 base 16: ffffffffffffffff
zero base 36: 0
Integer.MIN_VALUE base 10: -2147483648
Long.MIN_VALUE base 10: -9223372036854775808
Signed parse radix 16: -42
Unsigned parse hex: -1
Padded hex: 0000002a
```

The example demonstrates `int`/`long` formatting in common radices, falling back to radix 10 on an invalid argument, signed negative numbers versus unsigned hex bit patterns, boundary values, signed/unsigned round trips, and fixed hex width. The stdout strings reflect actual JDK behavior rather than guessing from `0x` notation in source code.

## 13. Practical application scenarios

### A. Displaying flags and bitmasks

When debugging flag states, you usually care more about the **bit pattern** than the signed value. For example:

```java
int flags = 0xA5000001;
String bitsHex = Integer.toHexString(flags); // a5000001
String allBitsHex = String.format(Locale.ROOT, "%08x", flags);
```

If you use `Integer.toString(flags,16)`, because the sign bit is 1, the string will start with `-` followed by digits representing the signed magnitude, rather than the 8-digit hex word of the bit pattern. Be clear about whether the log needs the **signed value** or the **raw bit pattern**.

### B. Building short identifiers in radix 36

For an existing **non-negative integer**:

```java
int id = 35;
String compact = Integer.toString(id, 36); // "z"
```

Base 36 can produce shorter strings than decimal for large numbers, but that is merely a **representation**. It does not provide security, increase entropy, or guarantee uniqueness beyond the source value. If uppercase letters, fixed width, or check digits must be preserved, those are additional rules of the protocol.

### C. Saving numeric values to files or JSON

When a protocol specifies decimal integers, `Integer.toString(value)` and `Long.toString(value)` produce stable strings without thousands separators. However, in JSON, **number** and **string** types differ: writing `"42"` is string data, whereas writing `42` is a numeric token. Do not decide the data schema solely based on formatter output.

For `long` numbers exceeding the contiguous integer precision of JavaScript `Number` (2^53), some systems choose to **transmit decimal strings** to avoid precision loss on the receiving side; this is a contract decision between systems, not a flaw of `Long.toString`.

### D. Reading/writing hex across two systems

If the sender uses `Integer.toHexString` for a bitmask and the receiver uses `Integer.parseInt`, errors can occur when the highest bit is 1. For an unsigned 32-bit pattern, use `Integer.parseUnsignedInt(text,16)` on the receiving side; for 64-bit `long`, use `Long.parseUnsignedLong` when matching the schema. Add prefixes or padding if the protocol requires them, but the receiver must properly understand the prefix and width.

## 14. Common mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Thinking `radix` changes the `int` value | It only changes the string representation | Distinguish numeric value from formatting |
| Expecting `toString(value,16)` to return `"0x..."` automatically | It only produces digits plus a sign if negative | Add the prefix intentionally or use a formatter |
| Expecting uppercase hexadecimal output | `toString` uses `a..z` | Use `toUpperCase(Locale.ROOT)` or `%X` when appropriate |
| Using radix 1/37 and expecting an exception | `toString` falls back to radix 10 | Validate radix if input can be invalid |
| Confusing `Integer.toString(-1,16)` and `Integer.toHexString(-1)` | `"-1"` differs from `"ffffffff"` | Choose signed vs bit-pattern format |
| Parsing `"ffffffff"` with `parseInt(...,16)` | Exceeds signed `Integer.MAX_VALUE` | Use `parseUnsignedInt(...,16)` |
| Parsing `"2a"` with radix 10 | The letter `a` is invalid | Pass the correct radix 16 |
| Reading `"0x2a"` with `parseInt(...,16)` | The parser does not automatically understand prefixes | Use `decode` or strip the prefix after validation |
| Using `Integer.toString((int) longValue)` | Casting can lose data before formatting | Use `Long.toString(longValue,radix)` |
| Using `Math.abs(MIN_VALUE)` yourself to format negatives | `abs` can overflow | Use the proper JDK API |
| Assuming `toString` auto-pads to a width | Results are minimal, unpadded | Use `Formatter`/`String.format` |
| Using `toString` for codes that preserve leading zeros | Cannot recover original width after parsing | Keep `String` or a width schema |
| Assuming `toString` creates "secure" strings | Radix 36 is just a representation | Design codes with dedicated security |
| Assuming any `String` from `toString` can be parsed with any radix | Requires matching radix and signedness | Store base metadata in the protocol |
| Confusing `Integer.valueOf` with `Integer.toString` | One returns a wrapper, the other returns a `String` | Check signatures and return types |
| Using `Integer.parseInt` when values exceed `int` | Out of range will throw an error | Choose `Long.parseLong` or `BigInteger` |

## 15. Self-check

1. What string does `Integer.toString(42,16)` return? Does it automatically add `0x`?
2. Are `Integer.toString(-42,16)` and `Integer.toHexString(-42)` the same or different? Explain in terms of signed value and bit pattern.
3. Why does `Integer.toString(255,1)` not throw an exception and instead return `"255"`? If an API needs to report an error on an invalid radix, what should you do?
4. What does `Long.toString(4_294_967_296L,16)` return? Why can't `Integer.toString((int) 4_294_967_296L,16)` be used to preserve the same value?
5. What results do the two calls `Integer.toUnsignedString(-1)` and `Integer.toString(-1)` produce? Does the underlying bit pattern change?
6. If you receive `"ffffffff"` as a 32-bit hex word, should you use `parseInt` or `parseUnsignedInt`? Why?
7. What is the radix-36 format of 35? Does it create a unique, secret, or fixed-length code?
8. When should you use `String.format(Locale.ROOT,"%08x", value)` instead of `Integer.toString(value,16)`?
9. Why can `"00042"` not be restored in its original form using `Integer.parseInt` followed by `Integer.toString`? In what situations should `String` be kept?
10. Write a signed round-trip test from `int` to base 2, 8, 10, 16 and back to `int`.
11. If the formatter uses radix 16 but the parser defaults to radix 10, what happens with `"2a"`?
12. If an application takes `radix` from user input, why should it validate within `2..36` instead of relying on `toString`'s fallback?
13. Why does `Integer.toString(value,16)` return lowercase letters? How do you produce uppercase without depending on locale?
14. When storing a bitmask that may be negative in a signed `int`, how should you format and parse it to preserve all 32 bits?

## 16. Official documentation

- [Java SE 17 — `Integer.toString(int, int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#toString(int,int)): radix 2..36, digits `0..9a..z`, negative sign, and radix 10 fallback.
- [Java SE 17 — `Long.toString(long, int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html#toString(long,int)): the same signed formatting rules for 64 bits.
- [Java SE 17 — `Integer.toUnsignedString`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#toUnsignedString(int,int)): unsigned interpretation of 32 bits.
- [Java SE 17 — `Integer.toHexString`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#toHexString(int)): unsigned hex string of an `int` bit pattern.
- [Java SE 17 — `Integer.parseInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#parseInt(java.lang.String,int)): parsing a signed string according to a radix.
- [Java SE 17 — `Formatter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html): rules for `%x`/`%X`, padding, width, and text formatting.

**Conclusion:** `Integer.toString` and `Long.toString` are APIs that convert an **integer value** into a **digit string according to a radix**; they do not change the value, do not automatically add prefixes, do not pad, and return lowercase letters for bases above 10. For negative numbers, `toString(value,radix)` uses a **minus sign**, while `toHexString`/`toBinaryString`/`toUnsignedString` are appropriate when you need to **represent the bit pattern in an unsigned sense**. Explicitly define signedness, radix, and protocol rules when formatting or parsing back, and validate the radix to avoid unwanted decimal fallbacks.