# formatHex and parseHex for Byte Arrays in Java 17

Java 17 provides the `HexFormat` class in the `java.util` package. This class converts between **byte arrays (`byte[]`)** and **hexadecimal (base-16) string representations** using two commonly used methods:

- `formatHex(byte[])`: formats bytes into a hex string.
- `parseHex(CharSequence)`: parses a hex string into a byte array.

Hex is commonly used when displaying binary data in technical logs, representing packet contents, working with byte sequences, encoding data in text formats, or inspecting data during debugging.

`HexFormat` is a standard API as of **Java 17**. For code targeting Java 17, you can use it directly without writing manual byte-conversion loops or relying on external libraries.

## 1. How Does Hexadecimal Represent a Byte?

A byte has 8 bits. Each hex digit represents 4 bits, so **one byte is represented by exactly two hex digits**.

| Byte value in bits | Unsigned decimal value | Hex representation |
| --- | ---: | --- |
| `0000 0000` | 0 | `00` |
| `0000 1010` | 10 | `0a` |
| `0111 1111` | 127 | `7f` |
| `1000 0000` | 128 | `80` |
| `1111 1111` | 255 | `ff` |

A 5-byte array like the one above can be represented as the string `000a7f80ff`. There is no delimiter by default: the first two characters are the first byte, the next two characters are the second byte, and so on.

Java declares the `byte` type as a signed integer in the range -128 to 127. However, when formatting a byte as hex, we want to represent the **8-bit pattern**, not write a minus sign. `HexFormat` handles this and produces exactly two digits per byte.

## 2. Using `HexFormat.of().formatHex()` to Convert a Byte Array to a String

A simple example:

```java
import java.util.HexFormat;

public class FormatBytes {
    public static void main(String[] args) {
        byte[] data = {
                0x00,
                0x0A,
                0x7F,
                (byte) 0x80,
                (byte) 0xFF
        };

        String hex = HexFormat.of().formatHex(data);

        System.out.println(hex);
    }
}
```

Output:

```text
000a7f80ff
```

Explanation:

- `HexFormat.of()` creates the default formatter.
- `formatHex(data)` converts each byte into two hex digits.
- By default, digits `a` through `f` are output in lowercase.
- The `data` array is not modified; the method returns a new `String`.

In the example, the values `0x80` and `0xFF` must be cast with `(byte)` because the corresponding integer literals exceed the positive range of `byte`.

### Switching to Uppercase

If you need an uppercase hex string:

```java
import java.util.HexFormat;

byte[] data = {(byte) 0x0A, (byte) 0xAF};

String lower = HexFormat.of().formatHex(data);
String upper = HexFormat.of().withUpperCase().formatHex(data);

System.out.println(lower); // 0aaf
System.out.println(upper); // 0AAF
```

`withUpperCase()` returns a `HexFormat` configured for uppercase. `HexFormat` is an immutable object; configuration methods like `withUpperCase()` create a new configured formatter without changing the original formatter.

You can use `withLowerCase()` to explicitly specify lowercase formatting, though that is also the default.

## 3. Using `parseHex()` to Recover a Byte Array

The reverse direction uses `parseHex()`:

```java
import java.util.HexFormat;
import java.util.Arrays;

public class ParseBytes {
    public static void main(String[] args) {
        String hex = "000a7f80ff";

        byte[] data = HexFormat.of().parseHex(hex);

        System.out.println(Arrays.toString(data));
    }
}
```

Output:

```text
[0, 10, 127, -128, -1]
```

Because `byte` in Java is a signed type, bytes whose highest bit is 1 are displayed as negative numbers. For example:

- Hex `80` corresponds to the bit pattern `1000 0000`, which has Java byte value -128.
- Hex `ff` corresponds to the bit pattern `1111 1111`, which has Java byte value -1.

This is not a conversion bug. The bit pattern is preserved; the decimal display of the `byte` type is signed.

If you want to print each byte's value in the unsigned range 0 to 255, use `Byte.toUnsignedInt()`:

```java
for (byte value : data) {
    System.out.println(Byte.toUnsignedInt(value));
}
```

Output:

```text
0
10
127
128
255
```

### Round-Trip: Formatting and Parsing Back

An important check is converting a byte array into a hex string and then parsing that string to get back the original byte array:

```java
import java.util.Arrays;
import java.util.HexFormat;

public class HexRoundTrip {
    public static void main(String[] args) {
        byte[] original = {
                0x00,
                0x0A,
                0x7F,
                (byte) 0x80,
                (byte) 0xFF
        };

        String hex = HexFormat.of().formatHex(original);
        byte[] restored = HexFormat.of().parseHex(hex);

        System.out.println(hex);
        System.out.println(Arrays.equals(original, restored));
    }
}
```

Output:

```text
000a7f80ff
true
```

With the default formatter, each byte is converted to two hex digits and `parseHex()` restores those exact bytes.

## 4. Complete Example with `formatHex()` and `parseHex()`

The following example combines both directions of conversion into a single program:

```java
import java.util.Arrays;
import java.util.HexFormat;

public class HexDemo {

    static String encode(byte[] bytes) {
        return HexFormat.of().formatHex(bytes);
    }

    static byte[] decode(String hex) {
        return HexFormat.of().parseHex(hex);
    }

    public static void main(String[] args) {
        byte[] original = {
                0x01,
                0x23,
                0x45,
                0x67,
                (byte) 0x89,
                (byte) 0xAB,
                (byte) 0xCD,
                (byte) 0xEF
        };

        String encoded = encode(original);
        byte[] decoded = decode(encoded);

        System.out.println("Hex: " + encoded);
        System.out.println("Bytes: " + Arrays.toString(decoded));
        System.out.println(
                "Restored accurately: " + Arrays.equals(original, decoded)
        );
    }
}
```

Output:

```text
Hex: 0123456789abcdef
Bytes: [1, 35, 69, 103, -119, -85, -51, -17]
Restored accurately: true
```

Compile and run with Java 17:

```bash
javac --release 17 -encoding UTF-8 HexDemo.java
java HexDemo
```

Use `--release 17` so the compiler restricts syntax and target APIs to Java 17. `HexFormat` is a built-in API starting from this version.

## 5. Customizing Delimiter, Prefix, Suffix, and Case

By default, `formatHex()` joins bytes contiguously. In some cases, a delimited string is easier to read, such as when displaying hardware addresses, packet bytes, or inspection data.

Using `withDelimiter()`:

```java
import java.util.HexFormat;

public class HexDelimiter {
    public static void main(String[] args) {
        byte[] data = {
                0x00,
                0x0A,
                0x7F,
                (byte) 0x80,
                (byte) 0xFF
        };

        HexFormat format = HexFormat.of()
                .withDelimiter(":")
                .withUpperCase();

        String hex = format.formatHex(data);

        System.out.println(hex);
    }
}
```

Output:

```text
00:0A:7F:80:FF
```

You can also configure a prefix and suffix:

```java
HexFormat format = HexFormat.of()
        .withDelimiter(" ")
        .withPrefix("0x")
        .withUpperCase();

String hex = format.formatHex(
        new byte[] {0x01, 0x02, (byte) 0xAF}
);

System.out.println(hex);
```

Output:

```text
0x01 0x02 0xAF
```

In this configuration:

- `withDelimiter(" ")` places a space between bytes.
- `withPrefix("0x")` adds a prefix to each byte.
- `withUpperCase()` formats hex digits in uppercase.

`withSuffix()` also lets you attach a suffix to each byte when formatting. Prefix, suffix, and delimiter are part of the formatter configuration, so you must use a formatter with the matching configuration when parsing the string.

### Parsing a Delimited String Back

Use the same formatter you created to parse:

```java
import java.util.HexFormat;
import java.util.Arrays;

public class ParseDelimitedHex {
    public static void main(String[] args) {
        HexFormat format = HexFormat.of()
                .withDelimiter(":")
                .withUpperCase();

        String text = "00:0A:7F:80:FF";

        byte[] bytes = format.parseHex(text);

        System.out.println(Arrays.toString(bytes));
        System.out.println(format.formatHex(bytes));
    }
}
```

Output:

```text
[0, 10, 127, -128, -1]
00:0A:7F:80:FF
```

If a string was produced with the `:` delimiter, do not use the default formatter to parse it because the default formatter expects contiguous hex pairs. Keep the formatter configuration consistent in both directions.

## 6. How Does `parseHex()` Handle Invalid Data?

`parseHex()` requires the input string to follow the formatter's format. Each byte must have two full hex digits, and the delimiter/prefix/suffix must match the configuration.

Example:

```java
import java.util.HexFormat;

public class InvalidHex {
    public static void main(String[] args) {
        HexFormat format = HexFormat.of();

        byte[] a = format.parseHex("0a");   // Valid
        byte[] b = format.parseHex("0AFF"); // Valid

        // The following lines throw IllegalArgumentException:
        // format.parseHex("0");    // Missing one digit of the byte
        // format.parseHex("0G");   // G is not a hex digit
        // format.parseHex("0a:ff");// Default formatter has no ":" delimiter
    }
}
```

Common errors:

| Input | Problem |
| --- | --- |
| `0` | Odd number of digits; does not form a complete byte. |
| `0G` | `G` is not a hexadecimal digit. |
| `0a:ff` with default formatter | Contains delimiter `:` when the formatter has no delimiter configured. |
| `0x0a` with default formatter | Contains prefix `0x` when the formatter expects no prefix. |
| `0A:0B` with formatter without delimiter | Structure does not match the formatter. |

When the string does not conform to the format, `parseHex()` throws `IllegalArgumentException`. If data may come from the network, files, or users, catch the exception at the appropriate boundary and handle it as invalid input.

Do not blindly strip all unfamiliar characters from the string before parsing, because doing so can cause malformed data to be interpreted as a different value that the sender did not intend.

## 7. Converting Part of an Array Using Indices

When you only need to format a slice of a byte array, use the overload taking `fromIndex` and `toIndex`:

```java
import java.util.HexFormat;

public class HexSlice {
    public static void main(String[] args) {
        byte[] packet = {
                0x10, 0x20, 0x30, 0x40, 0x50
        };

        String header = HexFormat.of().formatHex(packet, 0, 2);
        String payload = HexFormat.of().formatHex(packet, 2, 5);

        System.out.println(header);
        System.out.println(payload);
    }
}
```

Output:

```text
1020
304050
```

The index range uses the **inclusive start, exclusive end** convention: `fromIndex` is included, while `toIndex` is excluded. For example, `(packet, 2, 5)` processes indices 2, 3, and 4.

`parseHex()` also has an overload accepting a string and an index range:

```java
import java.util.HexFormat;
import java.util.Arrays;

public class ParseHexSlice {
    public static void main(String[] args) {
        String input = "xx00aaffyy";

        byte[] bytes = HexFormat.of().parseHex(input, 2, 8);

        System.out.println(Arrays.toString(bytes));
    }
}
```

Output:

```text
[0, -86, -1]
```

The character range from index 2 up to index 8 is `00aaff`, consisting of three bytes. The characters `xx` and `yy` outside the selected slice are not parsed.

Indices must fall within valid bounds of the array or string. If invalid indices are passed, the method throws an appropriate index exception. Use slice overloads only when you actually need to process part of the data; for an entire array or string, the simpler overload is easier to read.

## 8. Signed Bytes and Sign-Extension Pitfalls in Manual Conversion

One reason to use `HexFormat` is to avoid bugs when manually converting negative bytes into hex strings.

In Java, when a `byte` value is widened to `int`, its sign is preserved. For example:

```java
byte value = (byte) 0xFF;

System.out.println(value); // -1
System.out.println(Integer.toHexString(value));
```

The output of the second line may be:

```text
ffffffff
```

Reason: `value` is sign-extended to `int` -1, which has a 32-bit pattern of all 1s. `Integer.toHexString()` formats all 32 bits, producing eight `f` characters instead of the two digits `ff` needed for a single byte.

This can be handled manually by converting to an 8-bit unsigned number first:

```java
byte value = (byte) 0xFF;

String hex = Integer.toHexString(Byte.toUnsignedInt(value));

System.out.println(hex); // ff
```

However, when processing an entire array, `HexFormat.of().formatHex(bytes)` is simpler and less error-prone:

```java
byte[] data = {(byte) 0x80, (byte) 0xFF};

System.out.println(HexFormat.of().formatHex(data)); // 80ff
```

You do not need to manually mask each byte with `& 0xFF` when using `HexFormat`.

## 9. Hex Is Different from Text and Charsets

A byte array can contain binary data or text-encoded bytes. A hex string is only **a way of representing bytes**; it does not determine the original text on its own.

If you want to convert a Java string to hex, you must first choose a charset to turn the text into bytes:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class TextToHex {
    public static void main(String[] args) {
        String message = "Hello Java 17";

        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        String hex = HexFormat.of().formatHex(bytes);

        byte[] restoredBytes = HexFormat.of().parseHex(hex);
        String restoredText = new String(
                restoredBytes,
                StandardCharsets.UTF_8
        );

        System.out.println(hex);
        System.out.println(restoredText);
    }
}
```

Output:

```text
48656c6c6f204a617661203137
Hello Java 17
```

The conversion flow is:

```text
String
  |
  | getBytes(StandardCharsets.UTF_8)
  v
byte[]
  |
  | HexFormat.formatHex(...)
  v
Hex string
  |
  | HexFormat.parseHex(...)
  v
byte[]
  |
  | new String(bytes, StandardCharsets.UTF_8)
  v
Original String
```

The same charset must be used in both directions. If you encode with UTF-8 but decode with a different charset, the resulting string can have corrupted characters.

Do not use `new String(bytes)` without specifying a charset when consistent results across machines are needed. Explicitly specify `StandardCharsets.UTF_8` or the charset matching the data format.

### Hex Is Not Security Encryption

Converting bytes to hex **is not encryption**. Anyone with the hex string can call `parseHex()` to recover the original bytes.

- Hex encoding: represents bytes with characters that are easier to transmit/read.
- Encryption: transforms data using an algorithm and key to restrict access to those without the key.
- Hashing: produces a one-way digest via an algorithm; the original data cannot be recovered simply by "decoding."

Do not store passwords by converting passwords to hex. For passwords, use a dedicated password-hashing algorithm with salt and an appropriate work factor. Hex can only serve as a way to represent the byte output of another operation.

## 10. Handling Empty Arrays and Null Inputs

An empty array is valid data:

```java
byte[] empty = {};

String hex = HexFormat.of().formatHex(empty);
byte[] restored = HexFormat.of().parseHex(hex);

System.out.println("[" + hex + "]");
System.out.println(restored.length);
```

Output:

```text
[]
0
```

An empty hex string corresponds to an empty byte array. This is useful behavior when handling zero-length data fields.

Distinguish an empty array from a `null` reference. `HexFormat` does not turn `null` into an empty array; passing a null reference to its methods causes `NullPointerException`. If your API permits null, decide the policy clearly before calling:

```java
import java.util.HexFormat;
import java.util.Objects;

static String encode(byte[] bytes) {
    Objects.requireNonNull(bytes, "bytes must not be null");
    return HexFormat.of().formatHex(bytes);
}
```

Using `Objects.requireNonNull()` gives a clear error message right at the API boundary. If the business logic treats null as absent data, represent it separately using `Optional` or another explicit convention; do not silently confuse null with an empty array.

## 11. Reusing a Preconfigured Formatter

`HexFormat` is immutable and thread-safe, so a shared formatter can be stored in a constant:

```java
import java.util.HexFormat;

public final class HexCodec {
    private static final HexFormat HEX = HexFormat.of();

    private HexCodec() {
    }

    public static String encode(byte[] bytes) {
        return HEX.formatHex(bytes);
    }

    public static byte[] decode(String hex) {
        return HEX.parseHex(hex);
    }
}
```

If a communication format requires a delimiter and uppercase, you can declare a dedicated configuration:

```java
private static final HexFormat PACKET_HEX = HexFormat.of()
        .withDelimiter(":")
        .withUpperCase();
```

Keeping the configuration in one place prevents situations where one part of the application produces delimited strings while another part parses them with the default formatter.

Constant names and formatting policies should clearly indicate their purpose. For example, a formatter for debug logs may differ from a formatter for a protocol or file format.

## 12. Common Errors and How to Handle Them

| Symptom | Cause | Solution |
| --- | --- | --- |
| `cannot find symbol: HexFormat` | Compiling with a JDK/target API older than Java 17 or missing import. | Use a JDK supporting `--release 17` and `import java.util.HexFormat;`. |
| `IllegalArgumentException` when parsing | Contains non-hex characters, missing digits, or delimiter/prefix mismatch. | Validate the input data and use the exact formatter that created the string. |
| Result has `ff` but `byte` prints as `-1` | `byte` in Java is a signed number. | Use `Byte.toUnsignedInt()` if you want to display 0–255. |
| Manual conversion of negative byte yields `ffffffff` | Byte is sign-extended to `int` before calling `Integer.toHexString`. | Use `HexFormat`, or convert with `Byte.toUnsignedInt` if manual handling is necessary. |
| Parsing a string with `:` fails | The default formatter does not use that delimiter. | Use `HexFormat.ofDelimiter(":")` when parsing. |
| Parsing a string with `0x` fails | The formatter has no prefix configured. | Use a formatter with the corresponding `withPrefix("0x")`. |
| String after parsing back to text has garbled characters | Inconsistent charset used, or original bytes are not text in that charset. | Choose an explicit charset, such as UTF-8, for both encoding and decoding text. |
| Assuming hex protects secret data | Confusing encoding with encryption or hashing. | Use proper security mechanisms; hex does not conceal data. |

## 13. Practice Exercises

### Exercise 1 — Converting a Byte Array to Hex

Create the array:

```java
byte[] data = {
        0x01,
        0x02,
        0x0A,
        (byte) 0xFE
};
```

Use `HexFormat.of().formatHex(data)` to generate a hex string. Predict the output before running the program.

### Exercise 2 — Parsing and Comparing Byte Arrays

Given the string `"deadbeef"`. Do the following:

1. Parse it into `byte[]`.
2. Print the array using `Arrays.toString()`.
3. Format it back using `formatHex()`.
4. Compare the resulting string with the original string (case-insensitively if you changed the letter case).

### Exercise 3 — Formatter with a Delimiter

Create a formatter with delimiter `:` and uppercase. Convert `{0x01, 0x02, 0x03}` into a string. Then use the same formatter to parse it back and check with `Arrays.equals()`.

### Exercise 4 — Handling Invalid Data

Try parsing the strings:

- `"1"`
- `"0G"`
- `"00:ff"` using the default formatter.
- `"00:FF"` using the `:` delimiter formatter.

Determine which cases parse successfully and which cases throw `IllegalArgumentException`.

### Exercise 5 — Converting Text via UTF-8 and Hex

Convert the string `"Java 17"` to bytes using `StandardCharsets.UTF_8`, format it as hex, and parse it back. Use UTF-8 again to reconstruct the final string and compare it with the original string.

## 14. Quick Reference

| Need | Usage |
| --- | --- |
| Byte array to hex string | `HexFormat.of().formatHex(bytes)` |
| Hex string to byte array | `HexFormat.of().parseHex(hex)` |
| Uppercase formatting | `HexFormat.of().withUpperCase()` |
| Lowercase formatting | `HexFormat.of().withLowerCase()` |
| Adding a delimiter | `HexFormat.ofDelimiter(":")` or `withDelimiter()` |
| Adding prefix/suffix | `withPrefix()` and `withSuffix()` |
| Formatting a byte array slice | `formatHex(bytes, fromIndex, toIndex)` |
| Parsing a string slice | `parseHex(text, fromIndex, toIndex)` |
| Displaying a byte as unsigned | `Byte.toUnsignedInt(value)` |
| Converting text to bytes | `text.getBytes(StandardCharsets.UTF_8)` |
| Converting bytes to text | `new String(bytes, StandardCharsets.UTF_8)` |

**Core principle:** In Java 17, use `HexFormat` to convert byte arrays to hex strings and parse them back. `formatHex()` produces a two-digit representation per byte; `parseHex()` restores the bit pattern from a properly formatted string. If the data is text, specify the charset separately; if the data requires secrecy, use appropriate encryption because hex is only a representation, not security.
