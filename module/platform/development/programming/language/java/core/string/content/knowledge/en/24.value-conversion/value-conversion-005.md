# Integer.parseInt, Long.parseLong, and Radix in Java

## 1. From Character Strings to Integer Values

Input data from forms, configuration files, terminal commands, or APIs is often a `String`. The string `"123"` contains three characters, whereas the number `123` is an integer value that can be added, subtracted, compared, or used as an index. In Java:

- `Integer.parseInt(String s)` reads a **signed, base-10** numeric string and returns an `int`.
- `Long.parseLong(String s)` also reads a signed, base-10 numeric string but returns a `long`, which has a wider range.
- `Integer.parseInt(String s, int radix)` and `Long.parseLong(String s, int radix)` read the string according to a **caller-chosen radix**.

```java
int count = Integer.parseInt("123");
long distance = Long.parseLong("9000000000");
int binary = Integer.parseInt("101101", 2);

System.out.println(count);    // 123
System.out.println(distance); // 9000000000
System.out.println(binary);   // 45
```

Both methods return primitive integer values (`int` or `long`), without preserving original formatting such as leading `0`s or letter casing in hex strings. When `System.out.println` prints an `int` or `long` in the usual way, the result is displayed in decimal, even if the original string was parsed in another base.

## 2. What Is a Radix?

The radix (`radix`) specifies how many digit symbols exist and the place value of each position. For example, the string `101101` in base 2 represents:

\[
1\cdot 2^5 + 0\cdot 2^4 + 1\cdot 2^3 + 1\cdot 2^2 + 0\cdot 2^1 + 1\cdot 2^0 = 45.
\]

If `"101101"` is interpreted in base 10, the value is completely different. Therefore, **knowing the string alone is not enough; you must know its radix**.

Java allows `radix` from `Character.MIN_RADIX` = 2 to `Character.MAX_RADIX` = 36:

| Radix | Common name | Input string | Call | Numeric value |
| ---: | --- | --- | --- | ---: |
| 2 | Binary | `"101101"` | `Integer.parseInt("101101", 2)` | 45 |
| 8 | Octal | `"+77"` | `Integer.parseInt("+77", 8)` | 63 |
| 10 | Decimal | `"77"` | `Integer.parseInt("77", 10)` | 77 |
| 16 | Hexadecimal | `"7F"` | `Integer.parseInt("7F", 16)` | 127 |
| 36 | Base 36 | `"z"` | `Integer.parseInt("z", 36)` | 35 |

Bases up to 10 use the appropriate digits `0`–`9`. For bases greater than 10, the letters `a` through `z` represent values from 10 to 35. During parsing, uppercase and lowercase letters are equivalent: `Integer.parseInt("FF", 16)` and `Integer.parseInt("ff", 16)` both evaluate to 255.

Each digit must be **strictly less than the radix**. For example, `"19"` is invalid in base 8 because `9` is not an octal digit. An invalid radix such as 1 or 37 also triggers `NumberFormatException`.

**Omitting `radix` defaults to 10**: `Integer.parseInt("010")` returns 10; it does not automatically switch to base 8.

## 3. Plus Sign, Minus Sign, and Digits

A signed integer string may have `+` or `-` at the very beginning:

```java
System.out.println(Integer.parseInt("42"));      // 42
System.out.println(Integer.parseInt("+42"));     // 42
System.out.println(Integer.parseInt("-42"));     // -42
System.out.println(Integer.parseInt("-0"));      // 0
System.out.println(Integer.parseInt("-1A", 16)); // -26
```

In `"-1A"` in base 16, the digit portion `1A` represents 26 in base 10, and the minus sign turns the value into -26. Sign characters cannot appear in the middle or at the end of a number; `"+"` or `"-"` standing alone is also invalid input.

For positive numbers, the `+` sign is optional. The string `"-0"` parses to the integer `0`, because `int` and `long` do not have a separate negative zero value.

In base 16, forms such as `"f"`, `"F"`, and `"0f"` all describe the same value 15, but **the input string's formatting is not stored in the numeric value**.

## 4. 0x/0b Prefixes and Underscores Are Not Automatically Understood

In **Java source code**, developers can write the following literals:

```java
int a = 0xFF;
int b = 0b1010;
int c = 1_000;
```

However, runtime strings `"0xFF"`, `"0b1010"`, and `"1_000"` are not accepted directly by `parseInt`. This is the difference between **numeric literal syntax in source code** and **the input text format of the parse API**.

Correct:

```java
int a = Integer.parseInt("FF", 16);    // 255
int b = Integer.parseInt("1010", 2);  // 10
int c = Integer.parseInt("1000", 10); // 1000
```

Incorrect if called directly (the illustrative calls below will throw an exception):

```java
Integer.parseInt("0xFF", 16);
Integer.parseInt("0b1010", 2);
Integer.parseInt("1_000", 10);
```

If the data contract allows a `0x` prefix, **check for the prefix and strip it before parsing**:

```java
String input = "0xFF";
if (input.startsWith("0x") || input.startsWith("0X")) {
    input = input.substring(2);
}
int result = Integer.parseInt(input, 16);
System.out.println(result); // 255
```

This snippet illustrates **non-negative hex input**. If the data could be `"-0xFF"`, you must design separate sign-and-prefix handling rules to avoid slicing the string incorrectly. Java provides `Integer.decode`/`Long.decode`, which accept certain prefixes (and the leading-zero convention for octal), but they have a different contract from `parseInt(s, radix)`; do not switch APIs just to guess formats the user did not ask for.

## 5. int and long Have Different Ranges

`int` is a 32-bit signed integer; `long` is a 64-bit signed integer:

| Type | Minimum | Maximum |
| --- | ---: | ---: |
| `int` | -2,147,483,648 | 2,147,483,647 |
| `long` | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 |

Example:

```java
long validLong = Long.parseLong("9000000000");
System.out.println(validLong); // 9000000000
```

The string `"9000000000"` exceeds the `int` range but fits within `long`. Using `Integer.parseInt("9000000000")` produces `NumberFormatException`, not a truncated digit result.

Even when all characters are valid digits, **the value must still fit within the target type's range**:

```java
int maxInt = Integer.parseInt("7fffffff", 16);
int minInt = Integer.parseInt("-80000000", 16);

long maxLong = Long.parseLong("7fffffffffffffff", 16);
long minLong = Long.parseLong("-8000000000000000", 16);
```

The results are `Integer.MAX_VALUE`, `Integer.MIN_VALUE`, `Long.MAX_VALUE`, and `Long.MIN_VALUE`, respectively. Conversely, `Integer.parseInt("80000000", 16)` fails because it represents the positive value 2,147,483,648, exceeding `Integer.MAX_VALUE`.

`"ffffffff"` in base 16 is the positive value 4,294,967,295 without a minus sign, so `Integer.parseInt("ffffffff", 16)` also fails; `parseInt` does not automatically interpret this string as the bit pattern `-1`.

### When long is still not enough

`Long.parseLong` also checks the 64-bit signed range. For integers larger than `Long.MAX_VALUE`, use `java.math.BigInteger` when appropriate:

```java
import java.math.BigInteger;

BigInteger huge = new BigInteger("FFFFFFFFFFFFFFFF", 16);
System.out.println(huge); // 18446744073709551615
```

This snippet uses a separate `import`. `BigInteger` is an arbitrary-magnitude integer object whose arithmetic methods differ from primitive operators.

## 6. NumberFormatException: Causes and Handling

`Integer.parseInt` and `Long.parseLong` throw `NumberFormatException` if the string cannot be interpreted as a value of the target type in the requested radix.

Common errors:

| Input | Call | Why it fails |
| --- | --- | --- |
| `""` | `Integer.parseInt("")` | No digits. |
| `"+"` | `Integer.parseInt("+")` | Sign only, no digits. |
| `" 42 "` | `Integer.parseInt(" 42 ")` | Does not automatically strip whitespace. |
| `"12.5"` | `Integer.parseInt("12.5")` | Does not accept decimal fractions. |
| `"19"` | `Integer.parseInt("19", 8)` | Digit `9` is invalid in base 8. |
| `"0xFF"` | `Integer.parseInt("0xFF", 16)` | Does not treat `0x` as a prefix automatically. |
| `"1_000"` | `Integer.parseInt("1_000")` | Underscores are not accepted in strings. |
| `"2147483648"` | `Integer.parseInt("2147483648")` | Overflows the `int` range. |
| `"10"` | `Integer.parseInt("10", 1)` | Radix outside the range 2–36. |

Example of catching errors at an input boundary:

```java
String raw = "2147483648";

try {
    int value = Integer.parseInt(raw);
    System.out.println(value);
} catch (NumberFormatException ex) {
    System.out.println("Not a valid int");
}
```

The output is `Not a valid int`. There is no automatic mechanism turning invalid input into 0. A string exceeding the `int` range is explicitly rejected, preventing the application from silently using an unintended value.

`null` is also not a numeric value. Before processing input from forms or APIs, distinguish between **missing field**, **empty string**, **invalid string**, **out-of-range number**, and **valid number** according to business needs.

If the data specification permits extra whitespace, you can call `raw.strip()` (Java 11+) before parsing; if whitespace is a formatting error, report the error instead of silently fixing it. Do not write `catch (NumberFormatException e) { return 0; }` indiscriminately, as that equates "valid 0" with "invalid input".

## 7. Standalone Runnable Java 17+ Program

Save to `ParseRadixDemo.java`:

```java
import java.math.BigInteger;

public class ParseRadixDemo {
    private static void expectFailure(String label, String input, int radix) {
        try {
            Integer.parseInt(input, radix);
            System.out.println(label + ": unexpectedly accepted");
        } catch (NumberFormatException ex) {
            System.out.println(label + ": NumberFormatException");
        }
    }

    public static void main(String[] args) {
        System.out.println("decimal int: " + Integer.parseInt("120"));
        System.out.println("decimal long: " + Long.parseLong("9000000000"));
        System.out.println("binary: " + Integer.parseInt("101101", 2));
        System.out.println("octal: " + Integer.parseInt("+77", 8));
        System.out.println("hex: " + Integer.parseInt("7F", 16));
        System.out.println("hex signed: " + Integer.parseInt("-1A", 16));
        System.out.println("base36: " + Integer.parseInt("z", 36));
        System.out.println("int min hex: " +
                Integer.parseInt("-80000000", 16));
        System.out.println("long max hex: " +
                Long.parseLong("7fffffffffffffff", 16));
        System.out.println("long min hex: " +
                Long.parseLong("-8000000000000000", 16));

        System.out.println("hex prefix removed: " +
                Integer.parseInt("0xFF".substring(2), 16));

        String source = "prefix7fSuffix";
        System.out.println("slice: " +
                Integer.parseInt(source, 6, 8, 16));
        System.out.println("back to hex: " +
                Integer.toString(255, 16));

        System.out.println("unsigned int hex: " +
                Integer.toUnsignedString(-1, 16));
        System.out.println("unsigned long parsed: " +
                Long.toUnsignedString(
                        Long.parseUnsignedLong("ffffffffffffffff", 16)));

        expectFailure("prefix direct", "0xFF", 16);
        expectFailure("int overflow", "2147483648", 10);
        expectFailure("bad digit", "19", 8);
        expectFailure("spaces", " 42 ", 10);
        expectFailure("underscore", "1_000", 10);
        expectFailure("radix", "10", 1);

        // The Unicode escapes are Arabic-Indic digits 1, 2, 3.
        System.out.println("unicode digit: " +
                Integer.parseInt("\u0661\u0662\u0663", 10));

        System.out.println("big integer: " +
                new BigInteger("FFFFFFFFFFFFFFFF", 16));
    }
}
```

Compile and run:

```bash
javac ParseRadixDemo.java
java ParseRadixDemo
```

Output:

```text
decimal int: 120
decimal long: 9000000000
binary: 45
octal: 63
hex: 127
hex signed: -26
base36: 35
int min hex: -2147483648
long max hex: 9223372036854775807
long min hex: -9223372036854775808
hex prefix removed: 255
slice: 127
back to hex: ff
unsigned int hex: ffffffff
unsigned long parsed: 18446744073709551615
prefix direct: NumberFormatException
int overflow: NumberFormatException
bad digit: NumberFormatException
spaces: NumberFormatException
underscore: NumberFormatException
radix: NumberFormatException
unicode digit: 123
big integer: 18446744073709551615
```

In the program, invalid strings are passed to `expectFailure` to catch the exception and continue running subsequent examples. Valid strings are converted into values and printed, showing that a number can be read from various bases while still being represented as an ordinary integer.

In particular, `Integer.parseInt(source, 6, 8, 16)` reads the slice from index 6 (inclusive) to 8 (exclusive) of `"prefix7fSuffix"`, i.e., `"7f"` in base 16, which has value 127.

## 8. Overloads Reading a CharSequence Slice

Since Java 9, in addition to parsing an entire string, Java supports the overloads:

```text
Integer.parseInt(CharSequence s, int beginIndex, int endIndex, int radix)
Long.parseLong(CharSequence s, int beginIndex, int endIndex, int radix)
```

Example:

```java
String input = "id=7F;status=ok";
int value = Integer.parseInt(input, 3, 5, 16);
System.out.println(value); // 127
```

The slice `[3, 5)` is `"7F"`. This avoids creating an intermediate `substring` when processing part of a text buffer or `CharSequence`. For small strings, however, calling `substring(...)` and then parsing is completely fine if it is more readable.

When using indices, distinguish **out-of-bounds indices** or invalid index ranges (which can cause `IndexOutOfBoundsException`) from **slice content that is not a valid number** (which causes `NumberFormatException`). If input is untrusted, handle both possibilities.

## 9. Unsigned Parsing: Different from Signed Parsing

Some data formats store integers as **unsigned bit patterns**. This is a special case compared to standard `parseInt`/`parseLong`.

- `Integer.parseUnsignedInt(s, radix)` accepts values from 0 to \(2^{32}-1\).
- `Long.parseUnsignedLong(s, radix)` accepts values from 0 to \(2^{64}-1\).
- `Integer.toUnsignedString(value, radix)` and `Long.toUnsignedString(value, radix)` display bit patterns under unsigned interpretation.

Example:

```java
int bits = Integer.parseUnsignedInt("ffffffff", 16);
System.out.println(bits); // -1 if printed as signed int
System.out.println(Integer.toUnsignedString(bits));
// 4294967295

long longBits = Long.parseUnsignedLong("ffffffffffffffff", 16);
System.out.println(Long.toUnsignedString(longBits));
// 18446744073709551615
```

Java still stores `bits` in an `int` and `longBits` in a `long`; there are no `uint` or `ulong` primitive types. When printed or computed as signed values, the bit pattern above may appear as a negative number. If the application needs unsigned arithmetic, use the corresponding unsigned comparison/division and formatting methods, or choose `BigInteger` when large numbers need standard arithmetic.

**Do not use `parseUnsignedInt` merely to bypass a data error.** Only use it when the input contract genuinely specifies unsigned values.

## 10. Converting Back from Numbers to Strings by Radix

The `parseInt`/`parseLong` direction is **string → number**. The reverse direction is `Integer.toString(value, radix)` or `Long.toString(value, radix)`:

```java
int number = 255;

System.out.println(Integer.toString(number));     // 255
System.out.println(Integer.toString(number, 2));  // 11111111
System.out.println(Integer.toString(number, 8));  // 377
System.out.println(Integer.toString(number, 16)); // ff
System.out.println(Integer.toString(number, 36)); // 73
```

For negative numbers, understand the difference between **signed value** and **bit pattern**:

```java
System.out.println(Integer.toString(-1, 16));          // -1
System.out.println(Integer.toHexString(-1));           // ffffffff
System.out.println(Integer.toUnsignedString(-1, 16));  // ffffffff
```

`toString(-1, 16)` preserves the signed negative interpretation. `toHexString(-1)` and `toUnsignedString(-1, 16)` render the 32 bits as an unsigned value.

Converting to a number and back **does not preserve the original string's appearance**:

```java
int n = Integer.parseInt("000A", 16);
System.out.println(Integer.toString(n, 16)); // a
```

Leading `0`s and the uppercase `A` are gone. If that formatting is business-critical (identifiers, fixed-width numeric fields), keep the original string or apply custom formatting.

## 11. Unicode Digits and Input Validation

Java's digit parsing uses `Character.digit` rules. Certain Unicode digits outside the ASCII range are also accepted, for example:

```java
int n = Integer.parseInt("\u0661\u0662\u0663", 10);
System.out.println(n); // 123
```

The escape sequence corresponds to the three Arabic-Indic digits 1, 2, 3. This **does not mean** every numeric character worldwide is accepted by the parser, nor that the parser handles locale-specific grouping separators and decimal marks.

If a protocol format requires strictly ASCII digits `'0'` through `'9'`, validate that policy separately before parsing. Conversely, for internationalized input, do not assume only ASCII digits are valid. `Integer.parseInt` and `Long.parseLong` parse integers by radix, **not as a replacement for a localized number parser**.

## 12. Parsing Numbers and Checking Business Rules

A string that parses into a valid `int` may still be invalid for the application. For instance, a TCP port number must fall within the system-defined range; not every `int` value is a valid port number.

```java
static int parsePort(String raw) {
    final int port;
    try {
        port = Integer.parseInt(raw);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "Port must be a valid integer", ex);
    }

    if (port < 1 || port > 65535) {
        throw new IllegalArgumentException(
                "Port must be in range 1..65535");
    }
    return port;
}
```

This is an **illustrative method** placed inside a Java class; it is not a standalone program. The code checks syntax/`int` range via `parseInt`, then checks the port business rule within `1–65535`.

Also, distinguish `Integer.parseInt` (returns primitive `int`) from `Integer.valueOf` (returns `Integer` object), and `Long.parseLong` (returns `long`) from `Long.valueOf` (returns `Long`). Their string/radix overloads share the same parsing semantics but differ in return type. If you only need primitive integer arithmetic, `parseInt`/`parseLong` expresses the intent more directly.

## 13. Self-Check Exercises

Predict before running:

| Expression | Result |
| --- | --- |
| `Integer.parseInt("0012")` | `12` |
| `Integer.parseInt("010", 10)` | `10` |
| `Integer.parseInt("010", 2)` | `2` |
| `Integer.parseInt("+7f", 16)` | `127` |
| `Integer.parseInt("Z", 36)` | `35` |
| `Integer.parseInt("19", 8)` | `NumberFormatException` |
| `Integer.parseInt("2147483648")` | `NumberFormatException` |
| `Long.parseLong("2147483648")` | `2147483648` |
| `Integer.parseInt("0x10", 16)` | `NumberFormatException` |
| `Integer.toString(31, 16)` | `"1f"` |
| `Integer.toString(-31, 16)` | `"-1f"` |

Try building a function that accepts two input strings: a text number and a radix choice of 2, 8, 10, or 16. Parse to `int`, catch `NumberFormatException` to report a clear error, then print the result using `Integer.toString(value, 10)`. Test negative numbers, invalid digits for the radix, empty strings, whitespace, `0x` prefixes, and range overflow. Then extend it to `long` for comparison.

## 14. Key Takeaways

- `Integer.parseInt(s)` and `Long.parseLong(s)` read **signed base-10** integers; their return types are `int` and `long`, respectively.
- Overloads accepting `radix` support **bases 2–36**, enabling binary, octal, hexadecimal, and other bases.
- Digits must be valid for the radix, and **the value must fit within the target type's range**; bad syntax, invalid radix, or overflow throws `NumberFormatException`.
- Leading `+` and `-` signs are supported; `0x`/`0b` prefixes, underscores, whitespace, grouping separators, or fractional parts are not parsed directly.
- `Long.parseLong` has a wider range than `Integer.parseInt`; integers exceeding `long` require `BigInteger` or another data model.
- For **unsigned bit patterns**, use the corresponding `parseUnsignedInt`/`parseUnsignedLong` APIs; do not confuse unsigned and signed interpretations.
- `Integer.toString(value, radix)` and `Long.toString(value, radix)` convert numbers back to strings, but do not restore original formatting such as leading `0`s.