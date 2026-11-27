# Creating Default, Uppercase, or Lowercase HexFormat in Java 17

Java 17 adds the **`java.util.HexFormat`** class to convert byte arrays into hexadecimal (base-16) strings and parse hex strings back into bytes. This API is useful when displaying binary data in logs, inspecting payloads, reading data dumps, representing hashes, or exchanging data with external systems.

`HexFormat` lets you configure **lowercase or uppercase** digits, delimiters, prefixes, and suffixes. By default, `HexFormat.of()` uses **lowercase** hex digits with no delimiter, prefix, or suffix. For uppercase, use `withUpperCase()`; for explicit lowercase, use `withLowerCase()`.

This is an official API as of Java 17, not a preview feature, and requires no external libraries.

## 1. Hexadecimal and Byte Data

Hexadecimal uses 16 symbols:

~~~text
0 1 2 3 4 5 6 7 8 9 a b c d e f
~~~

One hex digit represents 4 bits (a nibble). Two hex digits represent 8 bits, corresponding to one byte.

| Byte (hex) | Binary | Signed byte value in Java |
| --- | --- | ---: |
| `00` | `00000000` | 0 |
| `0A` | `00001010` | 10 |
| `7F` | `01111111` | 127 |
| `80` | `10000000` | -128 |
| `FF` | `11111111` | -1 |

Java defines `byte` as an 8-bit signed integer in the range -128 to 127. When displaying byte data in hex, we want to see the full **8-bit pattern**. Therefore, a byte with Java value -1 is formatted as `ff`, not as a string with a minus sign.

~~~java
byte[] data = {
        0x00,
        0x0A,
        0x7F,
        (byte) 0x80,
        (byte) 0xFF
};
~~~

The array above has 5 bytes. Each byte needs two hex digits to represent its complete bit pattern.

## 2. Creating the Default HexFormat

Import the class:

~~~java
import java.util.HexFormat;
~~~

Create the default formatter and format an array:

~~~java
import java.util.HexFormat;

public class HexDefaultDemo {
    public static void main(String[] args) {
        byte[] data = {
                0x00, 0x0A, 0x7F, (byte) 0x80, (byte) 0xFF
        };

        HexFormat hex = HexFormat.of();

        String result = hex.formatHex(data);
        System.out.println(result);
    }
}
~~~

Output:

~~~text
000a7f80ff
~~~

Characteristics of `HexFormat.of()`:

- Uses digits `a` through `f` in **lowercase**.
- Adds no delimiter between bytes.
- Adds no prefix such as `0x`.
- Adds no suffix.
- Each byte is represented by exactly two hex digits.

For an array of `n` bytes, the default hex string has length `2n` characters. For example, a 5-byte array produces a 10-character string.

`HexFormat` is an immutable configuration object and is safe to share across threads. You can create one instance and reuse it across multiple methods instead of creating a new formatter for each conversion.

## 3. Creating an Uppercase HexFormat

To use digits `A` through `F`, call `withUpperCase()`:

~~~java
import java.util.HexFormat;

public class HexUpperCaseDemo {
    public static void main(String[] args) {
        byte[] data = {
                0x00, 0x0A, 0x7F, (byte) 0x80, (byte) 0xFF
        };

        HexFormat hex = HexFormat.of().withUpperCase();

        System.out.println(hex.formatHex(data));
    }
}
~~~

Output:

~~~text
000A7F80FF
~~~

`withUpperCase()` returns a `HexFormat` configured for uppercase. Because `HexFormat` is immutable, this call does not modify the original formatter; you can keep two separate configurations:

~~~java
HexFormat lower = HexFormat.of();
HexFormat upper = lower.withUpperCase();

byte[] data = {(byte) 0xAF};

System.out.println(lower.formatHex(data)); // af
System.out.println(upper.formatHex(data)); // AF
~~~

This is useful when the same data needs to be displayed under two different conventions, such as application logs using lowercase while technical specifications or protocols require uppercase.

## 4. Creating an Explicit Lowercase HexFormat

The default is already lowercase. However, the API also provides `withLowerCase()` to express intent explicitly:

~~~java
HexFormat hex = HexFormat.of().withLowerCase();
~~~

Example:

~~~java
byte[] data = {(byte) 0xAB, (byte) 0xCD, (byte) 0xEF};

String lower = HexFormat.of()
        .withLowerCase()
        .formatHex(data);

String upper = HexFormat.of()
        .withUpperCase()
        .formatHex(data);

System.out.println(lower); // abcdef
System.out.println(upper); // ABCDEF
~~~

You can use `withLowerCase()` when a formatter is derived from another configuration and you want to standardize the letter case. If the formatter is already `HexFormat.of()`, calling `withLowerCase()` does not change the output.

| Creation method | Hex digits | Example with byte `0xAF` |
| --- | --- | --- |
| `HexFormat.of()` | Default lowercase | `af` |
| `HexFormat.of().withLowerCase()` | Lowercase | `af` |
| `HexFormat.of().withUpperCase()` | Uppercase | `AF` |

## 5. Creating a Formatter with a Delimiter

By default, bytes are concatenated without separation. When readability matters, you can add a delimiter using `withDelimiter(...)` or the `ofDelimiter(...)` factory:

### 5.1. Using a Colon

~~~java
byte[] data = {(byte) 0x0A, (byte) 0xAF, (byte) 0xFF};

HexFormat hex = HexFormat.ofDelimiter(":");
System.out.println(hex.formatHex(data));
~~~

Output:

~~~text
0a:af:ff
~~~

### 5.2. Using Spaces or Hyphens

~~~java
HexFormat spaced = HexFormat.ofDelimiter(" ");
HexFormat dashed = HexFormat.ofDelimiter("-");

System.out.println(spaced.formatHex(data)); // 0a af ff
System.out.println(dashed.formatHex(data)); // 0a-af-ff
~~~

The delimiter is inserted **between bytes**, not at the start or end of the string.

### 5.3. Combining a Delimiter with Uppercase

~~~java
HexFormat hex = HexFormat.ofDelimiter(":")
        .withUpperCase();

System.out.println(hex.formatHex(data));
~~~

Output:

~~~text
0A:AF:FF
~~~

`ofDelimiter(":")` creates a formatter with a delimiter from the start. The equivalent call is `HexFormat.of().withDelimiter(":")`.

### 5.4. A Delimiter Can Be a Multi-Character String

~~~java
HexFormat hex = HexFormat.ofDelimiter(" | ")
        .withUpperCase();

System.out.println(hex.formatHex(data));
~~~

Output:

~~~text
0A | AF | FF
~~~

Choose a readable delimiter that matches the format expected by the receiving system. If you need to parse it back, use the formatter with the matching configuration.

## 6. Adding Prefix and Suffix

`HexFormat` allows adding a prefix and suffix to **each byte** with `withPrefix(...)` and `withSuffix(...)`.

~~~java
byte[] data = {(byte) 0x0A, (byte) 0xAF, (byte) 0xFF};

HexFormat hex = HexFormat.ofDelimiter(" ")
        .withPrefix("0x")
        .withUpperCase();

System.out.println(hex.formatHex(data));
~~~

Output:

~~~text
0x0A 0xAF 0xFF
~~~

The prefix `0x` is added before each byte, while the delimiter goes between bytes.

You can also add a suffix:

~~~java
HexFormat hex = HexFormat.ofDelimiter(", ")
        .withPrefix("[")
        .withSuffix("]");

System.out.println(hex.formatHex(data));
~~~

Output:

~~~text
[0a], [af], [ff]
~~~

Be sure to distinguish:

- `withPrefix("0x")` does not mean adding `0x` once before the entire array.
- `withSuffix(...)` adds a suffix to each byte.
- `withDelimiter(...)` is placed between two consecutive bytes.
- The default formatter has no prefix, suffix, or delimiter.

If a protocol requires a single shared prefix for the entire string, you can prepend it outside the formatter:

~~~java
String payload = "0x" + HexFormat.of().formatHex(data);
~~~

When parsing, strip that shared prefix first or design the input format accordingly.

## 7. Comprehensive Example: Same Data in Multiple Formats

~~~java
import java.util.HexFormat;

public class HexVariantsDemo {
    public static void main(String[] args) {
        byte[] data = {
                0x00, 0x0A, 0x7F, (byte) 0x80, (byte) 0xFF
        };

        HexFormat lower = HexFormat.of();
        HexFormat upper = HexFormat.of().withUpperCase();
        HexFormat colon = HexFormat.ofDelimiter(":");
        HexFormat upperColon = HexFormat.ofDelimiter(":")
                .withUpperCase();
        HexFormat prefixed = HexFormat.ofDelimiter(" ")
                .withPrefix("0x")
                .withUpperCase();

        System.out.println("default    = " + lower.formatHex(data));
        System.out.println("uppercase  = " + upper.formatHex(data));
        System.out.println("colon      = " + colon.formatHex(data));
        System.out.println("upperColon = " + upperColon.formatHex(data));
        System.out.println("prefixed   = " + prefixed.formatHex(data));
    }
}
~~~

Output:

~~~text
default    = 000a7f80ff
uppercase  = 000A7F80FF
colon      = 00:0a:7f:80:ff
upperColon = 00:0A:7F:80:FF
prefixed   = 0x00 0x0A 0x7F 0x80 0xFF
~~~

Only the formatter configuration changes; the input byte array stays the same. This is the benefit of separating data from display rules.

## 8. Converting a Hex String Back to Bytes with parseHex

`formatHex(...)` converts `byte[]` to a string. The reverse direction uses `parseHex(...)`:

~~~java
import java.util.Arrays;
import java.util.HexFormat;

public class HexParseDemo {
    public static void main(String[] args) {
        HexFormat hex = HexFormat.of();

        String text = "00aaff";
        byte[] data = hex.parseHex(text);

        System.out.println(Arrays.toString(data));
        System.out.println(hex.formatHex(data));
    }
}
~~~

Output:

~~~text
[0, -86, -1]
00aaff
~~~

The values `-86` and `-1` are how Java displays signed bytes. Their bit patterns are `0xAA` and `0xFF`, respectively.

### 8.1. Parsing Uppercase Strings

The default formatter can parse both uppercase and lowercase hex digits. Choosing uppercase/lowercase primarily affects **output formatting**, and does not restrict parsing input to a single letter case.

~~~java
byte[] bytes = HexFormat.of().parseHex("00Aaff");
~~~

### 8.2. Parsing Delimited Strings

When using a formatter with a delimiter, the input string must match that formatter's structure:

~~~java
HexFormat hex = HexFormat.ofDelimiter(":")
        .withUpperCase();

byte[] data = hex.parseHex("0A:AF:FF");
~~~

The formatter knows the delimiter is `:` and can split the bytes accordingly. Do not parse a delimited string with the default `HexFormat.of()`, because the default configuration expects contiguous hex digits.

### 8.3. Parsing Prefixes and Suffixes

If a formatter is configured with per-byte prefixes/suffixes, `parseHex(...)` uses that configuration as well:

~~~java
HexFormat hex = HexFormat.ofDelimiter(" ")
        .withPrefix("0x")
        .withUpperCase();

byte[] data = hex.parseHex("0x0A 0xAF 0xFF");
~~~

This is why you should use the same formatter configuration for both formatting and parsing when data is exchanged according to a specific convention.

### 8.4. Round-Trip

A useful property to verify is that data formatted and then parsed back must equal the original data:

~~~java
import java.util.Arrays;
import java.util.HexFormat;

byte[] original = {0x00, 0x01, (byte) 0x80, (byte) 0xFF};

HexFormat hex = HexFormat.ofDelimiter(":").withUpperCase();

String encoded = hex.formatHex(original);
byte[] decoded = hex.parseHex(encoded);

System.out.println(Arrays.equals(original, decoded)); // true
~~~

This round-trip is good for testing byte representation. It is not security encryption: a hex string is simply a representation of binary data, and anyone who reads the string can recover the original bytes.

## 9. Handling Invalid Hex Strings

`parseHex(...)` requires the input to conform to the structure described by the formatter. Common errors include:

- Containing characters that are not hex digits (`0`–`9`, `a`–`f`, `A`–`F`).
- Missing a digit in a byte.
- Wrong delimiter or missing delimiter between bytes.
- Prefix or suffix not matching the formatter being used.
- Input containing whitespace or separators not part of the configuration.

Examples with the default formatter:

~~~java
HexFormat hex = HexFormat.of();

hex.parseHex("abc");   // IllegalArgumentException: odd number of digits
hex.parseHex("0g");    // IllegalArgumentException: g is not a hex digit
hex.parseHex("00:ff"); // IllegalArgumentException: delimiter is not configured
~~~

When parsing data from users or external files, handle `IllegalArgumentException` at the input boundary:

~~~java
static byte[] decodeHex(String input) {
    try {
        return HexFormat.of().parseHex(input);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Invalid hex data", ex);
    }
}
~~~

Do not rely solely on checking string length. An even-length string can still contain invalid characters or malformed structure.

A `null` input is not a valid hex string and will cause `NullPointerException`; if your API requires a specific domain error message, check for null before calling the parser.

## 10. Formatting Part of a Byte Array

When you only need to display a region of an array, use the overload taking start and end indices:

~~~java
byte[] data = {
        (byte) 0xDE, (byte) 0xAD, (byte) 0xBE, (byte) 0xEF
};

HexFormat hex = HexFormat.of().withUpperCase();

System.out.println(hex.formatHex(data, 1, 3));
~~~

Output:

~~~text
ADBE
~~~

The index range uses the **inclusive `fromIndex`, exclusive `toIndex`** rule, matching standard range slicing in Java. In the example, elements at indices 1 and 2 are formatted; the element at index 3 is excluded.

The indices must be within array bounds and the start index must not exceed the end index. If the range is invalid, the API throws an index exception.

If you want to extract bytes before formatting, you could use `Arrays.copyOfRange`, but the range overload avoids allocating an intermediate array when you only need the display string.

## 11. HexFormat Does Not Determine Byte Order

A hex string shows the **order of bytes currently in the array**. It does not interpret multi-byte integers as big-endian or little-endian.

For example, the same integer `0x12345678` has two byte orderings:

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

HexFormat hex = HexFormat.of().withUpperCase();

System.out.println(hex.formatHex(bigEndian));    // 12345678
System.out.println(hex.formatHex(littleEndian)); // 78563412
~~~

Both strings are valid hex representations. The difference comes from the byte order chosen by `ByteBuffer.order(...)` before passing the array to `HexFormat`.

When reading protocols or binary files, you must know the byte order specified by the format. You cannot look at a hex string and deduce the original integer without knowing the byte order.

## 12. When to Use HexFormat Instead of Legacy Approaches?

Before Java 17, developers often looped over the byte array and called `String.format`, `Integer.toHexString`, or looked up a character table manually.

Example of a manual approach:

~~~java
static String toHex(byte[] bytes) {
    StringBuilder result = new StringBuilder();
    for (byte value : bytes) {
        result.append(String.format("%02x", value & 0xff));
    }
    return result.toString();
}
~~~

This works, but you must handle manually:

- Signed bytes via the `value & 0xff` mask.
- Two-digit width and leading zeros.
- Uppercase/lowercase.
- Delimiter, prefix, and suffix.
- Reverse parsing and invalid data checks.
- Performance when formatting many bytes.

With Java 17, `HexFormat` provides a dedicated and more readable API:

~~~java
String result = HexFormat.of().formatHex(bytes);
~~~

| Approach | Advantages | Limitations |
| --- | --- | --- |
| `HexFormat` | Standard API, format/parse, uppercase and delimiter configuration | Available from Java 17; older projects lack this API |
| `String.format` | Easy to customize format patterns | Repeated format calls have overhead; requires care with negative bytes |
| `Integer.toHexString` | Convenient for converting a single numeric value | Does not guarantee two digits per byte; requires handling sign and padding |
| Manual lookup table | Can be optimized for specialized cases | Must maintain logic and tests manually |

If the project targets Java 17 or later, prefer `HexFormat` for converting byte arrays to hex strings. If Java 8/11 support is required, consider compatible APIs or a dedicated library.

## 13. Is HexFormat Encryption or Hashing?

No. `HexFormat` only **converts the representation** of bytes into characters and back.

~~~java
byte[] secret = {0x01, 0x02, 0x03};
String hex = HexFormat.of().formatHex(secret);
byte[] restored = HexFormat.of().parseHex(hex);
~~~

Anyone with the string `010203` can recover the byte array. Hex does not provide:

- Security encryption.
- Confidentiality.
- Integrity.
- Digital signatures.
- Tamper resistance.

If you need hashing, use the APIs in `java.security.MessageDigest`; if you need encryption, use appropriate cryptographic APIs. Once you have the resulting hash or ciphertext as bytes, you can use `HexFormat` to **display** them.

Example of formatting a digest:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public class DigestHexDemo {
    public static void main(String[] args) throws NoSuchAlgorithmException {
        byte[] input = "Java 17".getBytes(StandardCharsets.UTF_8);

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(input);

        String hex = HexFormat.of().formatHex(hash);
        System.out.println(hex);
    }
}
~~~

The output is a hex string representing the SHA-256 bytes. The hash algorithm is performed by `MessageDigest`; `HexFormat` only formats the output.

## 14. Commonly Used Methods and Configurations

| API | Purpose |
| --- | --- |
| `HexFormat.of()` | Creates the default formatter, lowercase and no delimiter |
| `HexFormat.ofDelimiter(delimiter)` | Creates a formatter with a delimiter |
| `withUpperCase()` | Selects uppercase hex digits |
| `withLowerCase()` | Selects lowercase hex digits |
| `withDelimiter(delimiter)` | Sets the delimiter between bytes |
| `withPrefix(prefix)` | Sets the prefix before each byte |
| `withSuffix(suffix)` | Sets the suffix after each byte |
| `formatHex(bytes)` | Formats the entire byte array |
| `formatHex(bytes, from, to)` | Formats a slice of the array |
| `parseHex(text)` | Parses a string according to the formatter configuration |
| `toString()` | Returns a description of the formatter configuration |

The `with...` methods return a formatter configured accordingly; they do not modify the original instance. Multiple configurations can be chained:

~~~java
HexFormat wireFormat = HexFormat.ofDelimiter("-")
        .withUpperCase()
        .withPrefix("0x");
~~~

Because the formatter is immutable, it can be declared as a shared constant:

~~~java
private static final HexFormat HEX =
        HexFormat.of().withUpperCase();
~~~

There is no need to create a new instance on every `formatHex` call if the configuration does not change.

## 15. Practice Exercises

### Exercise 1 — Comparing Uppercase and Lowercase

Create the array:

~~~java
byte[] data = {0x01, 0x0A, (byte) 0xAF, (byte) 0xFF};
~~~

Print the array using `HexFormat.of()`, `withUpperCase()`, and `withLowerCase()`. Explain why the number of bytes does not change even though the displayed string differs.

### Exercise 2 — Adding a Delimiter

Use the `:` delimiter and produce:

~~~text
01:0a:af:ff
~~~

Then switch to uppercase:

~~~text
01:0A:AF:FF
~~~

### Exercise 3 — Prefix and Suffix

Create a formatter to display each byte in the form:

~~~text
[0x01] [0x0a] [0xaf] [0xff]
~~~

Try `withPrefix`, `withSuffix`, and `withDelimiter`. Distinguish per-byte prefix/suffix from a single shared prefix for the entire string.

### Exercise 4 — Round-Trip

Format an arbitrary byte array and parse it back. Use `Arrays.equals` to confirm the original array and restored array are equal. Repeat with a formatter that uses a delimiter and prefix.

### Exercise 5 — Handling Invalid Data

Try parsing the strings `abc`, `0g`, and `00:ff` using the default formatter. Catch `IllegalArgumentException` and display an appropriate error message.

### Exercise 6 — Byte Order

Use `ByteBuffer` to convert `0x12345678` into byte arrays in big-endian and little-endian. Print both with `HexFormat`, then explain why the two strings differ.

### Exercise 7 — Displaying a Hash

Compute a SHA-256 hash using `MessageDigest`, then format the digest as lowercase and uppercase hex. Explain why `HexFormat` does not perform the hashing algorithm.

## 16. Usage Principles

In Java 17, `HexFormat` is the standard API for representing and parsing byte data as hex. `HexFormat.of()` defaults to lowercase; `withUpperCase()` and `withLowerCase()` select digit casing; `withDelimiter()`, `withPrefix()`, and `withSuffix()` adjust per-byte formatting.

When using it:

- Use `formatHex(byte[])` to convert a byte array into a hex string.
- Use `parseHex(...)` to recover bytes from a string using the matching configuration.
- Reuse the formatter because it is immutable and safe to share.
- Remember that `byte` is signed in Java, whereas hex represents the 8-bit pattern.
- Distinguish byte order (endianness) from hex digit order.
- Handle invalid input strings at the data boundary.
- Do not treat hex as encryption or a security mechanism.

Separating binary data from display rules makes logging, testing, and integration with other systems more consistent.
