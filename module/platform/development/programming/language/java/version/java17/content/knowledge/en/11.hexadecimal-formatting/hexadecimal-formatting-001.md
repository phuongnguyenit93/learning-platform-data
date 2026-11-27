# The Role of HexFormat in Byte and Text Processing in Java 17

When working with binary data, developers often need to inspect a byte array as a human-readable character string, such as `48656c6c6f`, `48:65:6C:6C:6F`, or `0x48 0x65 0x6c`. Java 17 provides the **`java.util.HexFormat`** class to convert between **bytes and hexadecimal (base-16) representation** in a consistent way.

`HexFormat` was added in JDK 17. This class helps you:

- Convert `byte[]` to a hex string using `formatHex(...)`.
- Convert a hex string back to `byte[]` using `parseHex(...)`.
- Choose uppercase or lowercase for hex digits.
- Configure a delimiter, prefix, and suffix for each byte.
- Process only a slice of a byte array or input string when needed.

Hexadecimal is a **data representation**, not security encryption. A hex string can be converted back to the exact original bytes; anyone who has the string can recover the data. Therefore, `HexFormat` is useful for debugging, logging, displaying bytes, inspecting hashes, working with binary protocols, or representing data in documentation.

## 1. Hexadecimal and Its Relationship to Bytes

A byte has 8 bits, so there are 256 distinct bit patterns, from `00000000` to `11111111`. One hexadecimal digit represents 4 bits:

| Hex | Binary | Decimal value |
| --- | --- | ---: |
| `0` | `0000` | 0 |
| `1` | `0001` | 1 |
| `9` | `1001` | 9 |
| `A` | `1010` | 10 |
| `B` | `1011` | 11 |
| `C` | `1100` | 12 |
| `D` | `1101` | 13 |
| `E` | `1110` | 14 |
| `F` | `1111` | 15 |

Because a byte has 8 bits, it is represented by **two hex digits**. For example:

| Byte (binary) | Hex | Unsigned decimal |
| --- | --- | ---: |
| `0000 0000` | `00` | 0 |
| `0000 1010` | `0A` | 10 |
| `0100 1000` | `48` | 72 |
| `0111 1111` | `7F` | 127 |
| `1000 0000` | `80` | 128 |
| `1111 1111` | `FF` | 255 |

In Java, the `byte` type is an 8-bit signed integer with a range from -128 to 127. However, when representing a byte in hex, we care about its **8-bit pattern**. Therefore:

- A `byte` with value `72` is represented as `48`.
- A `byte` with value `-1` has the bit pattern `11111111`, represented as `FF` or `ff`.
- Every byte always produces two hex digits, even when the byte is less than `0x10`, such as `0A`.

Example of a byte sequence:

```text
Byte:  0x48  0x65  0x6C  0x6C  0x6F
ASCII:   H     e     l     l     o
Text:  Hello
Hex:   48 65 6c 6c 6f
```

Hex lets you see the exact bytes being transmitted or stored. It does not by itself indicate whether the data is text, an image, an integer, a key, or a protocol structure; interpretation depends on the application's format.

## 2. HexFormat in Java 17

The class is in the `java.util` package:

```java
import java.util.HexFormat;
```

To use the default configuration:

```java
HexFormat hex = HexFormat.of();
```

`HexFormat.of()` creates a default formatter:

- Uses **lowercase** hex digits (`a` through `f`).
- Adds no delimiter between bytes.
- Adds no prefix or suffix to bytes.

Example:

```java
import java.util.HexFormat;

public class HexFormatBasic {
    public static void main(String[] args) {
        byte[] bytes = {0x48, 0x65, 0x6C, 0x6C, 0x6F};

        HexFormat hex = HexFormat.of();
        String encoded = hex.formatHex(bytes);

        System.out.println(encoded);
    }
}
```

Output:

```text
48656c6c6f
```

`formatHex` joins the two hex digits of each byte in array order. An array of 5 bytes produces a string of 10 hex characters. If the array is empty, the result is an empty string.

## 3. Converting byte[] to a Hex String with formatHex

### 3.1. Converting the Entire Array

The most commonly used method:

```java
String hexText = HexFormat.of().formatHex(bytes);
```

Each byte is converted into two hex characters. The byte order in the array is preserved; `HexFormat` does not reorder bytes by endianness.

```java
byte[] data = {
        0x00, 0x01, 0x0A, 0x10, 0x7F, (byte) 0x80, (byte) 0xFF
};

String text = HexFormat.of().formatHex(data);
System.out.println(text);
```

Output:

```text
00010a107f80ff
```

Two points to note:

1. The byte `0x0A` is written in full as `0a`, not shortened to `a`.
2. Hex values from `0x80` to `0xFF` require a `(byte)` cast when writing literals larger than the positive range of `byte`.

### 3.2. Converting Only a Slice of the Array

If only a region of data is needed, you can specify the start and end indices:

```java
byte[] packet = {
        0x01, 0x02, 0x48, 0x65, 0x6C, 0x6C, 0x6F, 0x7F
};

String payloadHex = HexFormat.of().formatHex(packet, 2, 7);
System.out.println(payloadHex);
```

Output:

```text
48656c6c6f
```

The range follows the **`fromIndex` inclusive, `toIndex` exclusive** rule:

- Starts taking elements at `fromIndex`.
- Stops before `toIndex`.
- The length of the converted slice is `toIndex - fromIndex`.

In the example, index `2` is included, while index `7` is excluded. The method checks array bounds; negative indices, indices exceeding the length, or an invalid index range will throw `IndexOutOfBoundsException`.

### 3.3. Writing Output to an Appendable

In addition to returning a `String`, `HexFormat` provides an overload that writes to an `Appendable`:

```java
import java.io.IOException;
import java.util.HexFormat;

public class HexAppendable {
    public static void main(String[] args) throws IOException {
        byte[] bytes = {0x01, 0x23, (byte) 0xFE};
        StringBuilder output = new StringBuilder();

        HexFormat.of().formatHex(output, bytes);
        System.out.println(output);
    }
}
```

Output:

```text
0123fe
```

`StringBuilder` implements `Appendable`, so it can be used to append the result to content already being built. This is useful when appending multiple byte regions sequentially into the same buffer instead of creating multiple intermediate strings. The overload taking an `Appendable` can throw `IOException` according to the `Appendable` contract.

## 4. Converting a Hex String Back to Bytes with parseHex

Converting in the reverse direction uses `parseHex(...)`:

```java
byte[] bytes = HexFormat.of().parseHex("48656c6c6f");
```

Complete example:

```java
import java.util.Arrays;
import java.util.HexFormat;

public class HexParseBasic {
    public static void main(String[] args) {
        String encoded = "48656c6c6f";
        byte[] bytes = HexFormat.of().parseHex(encoded);

        System.out.println(Arrays.toString(bytes));
        System.out.println(HexFormat.of().formatHex(bytes));
    }
}
```

Output:

```text
[72, 101, 108, 108, 111]
48656c6c6f
```

The bytes in the array are displayed as signed numbers by `Arrays.toString(byte[])`; that does not alter the bit pattern of the bytes. To display them in hex, use `formatHex`.

### 4.1. Input String Must Have the Appropriate Digit Count

Each byte corresponds to two hex digits. Therefore, a default hex string must have an **even number of characters**:

```java
byte[] valid = HexFormat.of().parseHex("0a7f"); // 2 bytes

// An odd-length string cannot be split into byte pairs:
// byte[] invalid = HexFormat.of().parseHex("abc");
```

If the string contains non-hex-digit characters, or if its delimiter/prefix/suffix structure does not match the formatter, `parseHex` throws `IllegalArgumentException`. Do not ignore the exception and assume the data was fully decoded.

### 4.2. Uppercase and Lowercase Handling When Parsing

Hexadecimal allows both `a`–`f` and `A`–`F`. The default formatter produces lowercase, but the parser can read both uppercase and lowercase hex digits:

```java
import java.util.Arrays;
import java.util.HexFormat;

HexFormat hex = HexFormat.of();

byte[] lower = hex.parseHex("0aff");
byte[] upper = hex.parseHex("0AFF");

System.out.println(Arrays.equals(lower, upper)); // true
```

`withUpperCase()` and `withLowerCase()` determine how hex letters are **formatted**. They do not turn two valid hex representations into two different byte sequences.

### 4.3. Parsing a String Slice

You can parse only a slice of a `CharSequence`:

```java
String frame = "HDR:48656c6c6f:END";

// Range [4, 14) is the string "48656c6c6f".
byte[] payload = HexFormat.of().parseHex(frame, 4, 14);

System.out.println(new String(
        payload, java.nio.charset.StandardCharsets.UTF_8
));
```

Output:

```text
Hello
```

This operates on a character range of the source string; `fromIndex` and `toIndex` still follow the inclusive-start, exclusive-end rule. The parsed slice must contain a valid hex string according to the `HexFormat` configuration.

## 5. Customizing Uppercase and Lowercase

By default, `HexFormat.of()` uses lowercase. You can create an uppercase formatter:

```java
HexFormat lower = HexFormat.of();
HexFormat upper = HexFormat.of().withUpperCase();

byte[] bytes = {0x0A, 0x2B, (byte) 0xCD};

System.out.println(lower.formatHex(bytes));
System.out.println(upper.formatHex(bytes));
```

Output:

```text
0a2bcd
0A2BCD
```

`withUpperCase()` and `withLowerCase()` return a `HexFormat` configured accordingly. Formatters are immutable objects; you can store a configured formatter in a `static final` constant for reuse.

```java
private static final HexFormat HEX_UPPER =
        HexFormat.of().withUpperCase();
```

Uppercase or lowercase is merely a display convention. The two strings `0a2bcd` and `0A2BCD` represent the exact same sequence of bytes.

## 6. Adding Delimiter, Prefix, and Suffix

In logs or technical documentation, contiguous hex strings can be hard to read. `HexFormat` lets you configure:

- **Delimiter:** the separator string placed between bytes.
- **Prefix:** the string placed before each byte's hex digits.
- **Suffix:** the string placed after each byte's hex digits.

### 6.1. Adding a Separator Between Bytes

```java
byte[] bytes = {0x48, 0x65, 0x6C, 0x6C, 0x6F};

HexFormat colon = HexFormat.ofDelimiter(":");
HexFormat space = HexFormat.ofDelimiter(" ");

System.out.println(colon.formatHex(bytes));
System.out.println(space.formatHex(bytes));
```

Output:

```text
48:65:6c:6c:6f
48 65 6c 6c 6f
```

The delimiter is inserted **between bytes**, not at the start or end of the entire string.

### 6.2. Adding a Prefix to Each Byte

```java
HexFormat prefixed = HexFormat.of()
        .withDelimiter(" ")
        .withPrefix("0x")
        .withUpperCase();

byte[] bytes = {0x01, 0x0A, (byte) 0xFF};
System.out.println(prefixed.formatHex(bytes));
```

Output:

```text
0x01 0x0A 0xFF
```

The `0x` prefix appears before **each byte**, because every element is formatted independently. For contiguous bytes without a delimiter, `withPrefix("0x")` produces output like `0x010x0a0xff`.

### 6.3. Adding a Suffix to Each Byte

```java
HexFormat bracketed = HexFormat.of()
        .withDelimiter(", ")
        .withPrefix("[")
        .withSuffix("]");

byte[] bytes = {0x01, 0x02, 0x03};
System.out.println(bracketed.formatHex(bytes));
```

Output:

```text
[01], [02], [03]
```

The prefix and suffix are applied to each byte; the delimiter goes between the formatted bytes. This makes it easy to produce arbitrary display formats without manually looping and concatenating strings.

### 6.4. Combining Configurations

```java
HexFormat packetView = HexFormat.of()
        .withDelimiter(" | ")
        .withPrefix("0x")
        .withSuffix("")
        .withUpperCase();

byte[] packet = {0x01, 0x02, 0x10, (byte) 0xFE};
System.out.println(packetView.formatHex(packet));
```

Output:

```text
0x01 | 0x02 | 0x10 | 0xFE
```

The `with...` methods can be chained to build a readable formatter. Because `HexFormat` is immutable, each call returns a new configuration without modifying the original formatter.

## 7. Parsing Strings with Delimiter, Prefix, and Suffix

A formatter with a matching configuration can parse the format that it produces:

```java
HexFormat format = HexFormat.of()
        .withDelimiter(":")
        .withPrefix("0x")
        .withUpperCase();

String text = "0x48:0x65:0x6C:0x6C:0x6F";
byte[] bytes = format.parseHex(text);

System.out.println(format.formatHex(bytes));
```

Output:

```text
0x48:0x65:0x6C:0x6C:0x6F
```

The parser uses the formatter's delimiter, prefix, and suffix to recognize the structure. If the input format does not match, the data will not be parsed as expected and may throw `IllegalArgumentException`.

### 7.1. The Default Formatter Does Not Automatically Strip `0x`

A common string in documentation is `0x48656c6c6f`. However, `HexFormat.of()` has no prefix by default:

```java
// Cannot be parsed by the default formatter:
// HexFormat.of().parseHex("0x48656c6c6f");

HexFormat prefixed = HexFormat.of().withPrefix("0x");
byte[] bytes = prefixed.parseHex("0x48656c6c6f");
```

If the format has a prefix on each byte and a delimiter, both must be configured properly:

```java
HexFormat format = HexFormat.of()
        .withPrefix("0x")
        .withDelimiter(" ");

byte[] bytes = format.parseHex("0x48 0x65 0x6c");
```

Do not strip characters at fixed positions when the source format is unknown. Configuring the formatter explicitly expresses the expected prefix/delimiter and keeps formatting and parsing consistent.

### 7.2. Letter Case Is Not a Delimiter

The parser accepts uppercase or lowercase hex digits; the uppercase setting mainly controls how strings are formatted on output. For example, an uppercase formatter can parse a lowercase string as long as the delimiter/prefix/suffix still match.

## 8. HexFormat and Text: Bytes Are Not Automatically Characters

A common mistake is assuming that the hex representation of a text string is directly its Unicode character codes. In practice, the workflow must distinguish:

1. **Text** is a sequence of Java characters (`String`).
2. A **charset** such as UTF-8 converts text into bytes.
3. `HexFormat` represents those bytes as hex digits.

To convert a text string to hex, encode it using an explicit charset first:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String message = "Xin chào";
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);

String hexText = HexFormat.of().formatHex(bytes);
System.out.println(hexText);
```

To recover the text, parse the hex into bytes and then decode using the **same charset**:

```java
byte[] restoredBytes = HexFormat.of().parseHex(hexText);
String restoredText = new String(
        restoredBytes, StandardCharsets.UTF_8
);

System.out.println(restoredText);
```

If UTF-8 is used when encoding, UTF-8 must also be used when decoding. Do not use `new String(bytes)` or `getBytes()` without passing a charset when consistent results across machines are needed, because those overloads depend on the environment's default charset.

### 8.1. Complete Example: String ↔ UTF-8 bytes ↔ hex

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class TextToHex {
    public static void main(String[] args) {
        String original = "Java 17 - Xin chào";

        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
        String hex = HexFormat.of().formatHex(utf8);

        byte[] decodedBytes = HexFormat.of().parseHex(hex);
        String restored = new String(
                decodedBytes, StandardCharsets.UTF_8
        );

        System.out.println("Original: " + original);
        System.out.println("Hex:      " + hex);
        System.out.println("Restored: " + restored);
    }
}
```

The exact hex string depends on the UTF-8 bytes; Vietnamese accented characters can occupy multiple bytes. The `restored` result recovers the content if the original bytes were valid UTF-8.

### 8.2. Hex Is Not Synonymous with ASCII

Basic ASCII characters have byte codes corresponding to their values, such as `A` being `41`. However, accented Vietnamese characters, emojis, and many other Unicode characters are often encoded as multiple UTF-8 bytes. Therefore, you cannot take each hex pair and cast it into a single Java character assuming ASCII.

Example:

```java
String text = "é";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
System.out.println(HexFormat.of().formatHex(utf8));
```

With UTF-8, the precomposed Unicode character `é` is encoded into two bytes `c3 a9`, so the hex string is `c3a9`. Hex shows the **byte encoding**, not directly the code point of a Java `char`.

## 9. Role in Debugging, Logging, and Binary Protocols

### 9.1. Inspecting a Packet or Byte Buffer

When receiving data from a socket, file, or binary API, hex makes it easy to read the bytes in order:

```java
byte[] packet = {
        0x01, 0x10, 0x00, 0x2A,
        0x48, 0x69, (byte) 0xFF
};

String dump = HexFormat.ofDelimiter(" ")
        .withUpperCase()
        .formatHex(packet);

System.out.println(dump);
```

Output:

```text
01 10 00 2A 48 69 FF
```

This is a quick way to compare against protocol documentation, device logs, or expected test data. `HexFormat` does not parse packet structure; you still need to know which bytes are the header, length, payload, checksum, or status flags.

### 9.2. Logging Only the Payload Region

If an array contains a header and payload, you can format only the payload:

```java
int payloadStart = 4;
int payloadEnd = packet.length - 1; // Exclude the trailing checksum byte

String payloadDump = HexFormat.ofDelimiter(" ")
        .formatHex(packet, payloadStart, payloadEnd);
```

The end index `payloadEnd` is exclusive. You must compute indices from the actual protocol layout and validate bounds before calling the method.

### 9.3. Formatting a Hash or Checksum for Display

A hash value is a sequence of bytes. You can display it in hex:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public class DigestHex {
    public static void main(String[] args)
            throws NoSuchAlgorithmException {
        byte[] input = "sample".getBytes(StandardCharsets.UTF_8);
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(input);

        String hexDigest = HexFormat.of().formatHex(digest);
        System.out.println(hexDigest);
    }
}
```

`MessageDigest` computes the digest; `HexFormat` only converts the digest array into a readable string. **Do not confuse HexFormat with a hash algorithm**, and do not use hex as a security measure. A hash cannot be created merely by converting bytes to hex.

## 10. Signed Bytes, Byte Order, and Endianness

`HexFormat` formats each `byte` element according to its 8-bit pattern. It does not determine how a group of bytes is interpreted as a multi-byte integer.

Example:

```java
byte[] bytes = {(byte) 0x01, (byte) 0x02, (byte) 0x03, (byte) 0x04};
System.out.println(HexFormat.ofDelimiter(" ").formatHex(bytes));
```

Output:

```text
01 02 03 04
```

This string preserves the exact order of elements in the array. If a protocol treats those four bytes as a 32-bit integer:

- Big-endian may interpret them as `0x01020304`.
- Little-endian may interpret them as `0x04030201`.

`HexFormat` still displays `01 02 03 04` in both cases; endianness interpretation belongs to the number-reading code, such as `ByteBuffer.order(...)`, not `HexFormat`.

Additionally, `byte` is a signed type in Java. If printed directly with `System.out.println(bytes[i])`, the value `0xFF` appears as `-1`; `HexFormat` still prints `ff` because it represents the 8-bit pattern.

## 11. Immutability and Formatter Reuse

`HexFormat` is immutable and thread-safe. Configuration methods such as:

- `withDelimiter(String)`
- `withPrefix(String)`
- `withSuffix(String)`
- `withUpperCase()`
- `withLowerCase()`

return a new formatter. They do not modify the original formatter.

Example:

```java
HexFormat base = HexFormat.of();
HexFormat colonUpper = base.withDelimiter(":").withUpperCase();

byte[] bytes = {0x0A, 0x0B};

System.out.println(base.formatHex(bytes));
System.out.println(colonUpper.formatHex(bytes));
```

Output:

```text
0a0b
0A:0B
```

Because a formatter holds no mutable state between calls, you can declare shared formatters:

```java
private static final HexFormat HEX =
        HexFormat.of().withUpperCase();
```

This helps keep logging or communication formatting consistent across modules.

## 12. Error Handling When Parsing Untrusted Data

Hex strings coming from files, users, or the network can be malformed. Common errors include:

- An odd number of hex characters in the default format.
- Characters outside `0`–`9`, `a`–`f`, `A`–`F`.
- Missing configured prefix, suffix, or delimiter.
- A delimiter in the wrong position.
- Invalid slice indices on input.

You can catch `IllegalArgumentException` at the data boundary:

```java
import java.util.HexFormat;

static byte[] tryParseHex(String input) {
    try {
        return HexFormat.of().parseHex(input);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Input must be a valid hex string", ex
        );
    }
}
```

In real applications, define the input contract before parsing: are spaces, colons, `0x`, or uppercase letters allowed? Configure `HexFormat` accordingly or normalize according to a clearly published rule. Do not arbitrarily strip all non-hex characters; doing so can turn invalid data into a different string that the sender never intended to send.

If the data can be large, check length limits before allocating byte arrays to avoid receiving an unexpectedly huge string. `HexFormat` is a conversion utility, not a replacement for size and protocol-rule validation.

## 13. Comparing HexFormat with the Manual Approach

Before Java 17, you typically had to write a loop and look up a character table manually:

```java
static String toHexManually(byte[] bytes) {
    char[] digits = "0123456789abcdef".toCharArray();
    StringBuilder result = new StringBuilder(bytes.length * 2);

    for (byte value : bytes) {
        int unsigned = value & 0xFF;
        result.append(digits[unsigned >>> 4]);
        result.append(digits[unsigned & 0x0F]);
    }

    return result.toString();
}
```

That code had to handle manually:

1. Converting a signed byte to a value in 0–255 using `& 0xFF`.
2. Extracting the high 4 bits via right shift.
3. Extracting the low 4 bits via bitmasking.
4. Selecting characters from the digit lookup table.
5. Producing a full two-digit representation for each byte.
6. Adding extra logic if a delimiter, prefix, suffix, or uppercase was needed.

In Java 17, `HexFormat` expresses the intent directly:

```java
String hex = HexFormat.of().formatHex(bytes);
```

For new code, `HexFormat` reduces boilerplate and unifies formatting/parsing behavior. Manual loops should only be kept when a specialized format not provided by the API is needed, or when there is a measured and verified performance reason.

## 14. Misconceptions to Avoid

| Misconception | Correct understanding |
| --- | --- |
| `HexFormat` converts Unicode text directly to hex. | It takes bytes; to represent text, first encode the `String` using a charset such as UTF-8. |
| Hex is security encryption. | Hex is just a reversible encoding; it does not hide data. |
| A byte only needs one hex digit if its value is small. | `HexFormat` always represents each byte with two digits, such as `0a`. |
| If a `byte` has a negative value, its hex is also negative. | Hex shows the 8-bit pattern; `-1` is written as `ff`. |
| `formatHex` automatically changes endianness. | It preserves the order of bytes in the array. |
| The default formatter automatically strips `0x` or `:`. | You must configure the corresponding prefix/delimiter; the default is a contiguous hex string. |
| `withUpperCase()` changes the underlying bytes. | It only changes how hex letters are displayed. |
| A prefix only appears once at the start of the entire string. | Prefix/suffix apply to each byte; the delimiter separates bytes. |
| `parseHex` automatically ignores arbitrary whitespace. | The parser follows the formatter configuration; the default format has no delimiter. |
| A valid hex string means a valid payload. | Parsing only validates hex syntax; payload structure and meaning must be checked separately. |

## 15. Practice Exercises

### Exercise 1 — Converting Bytes to Hex

Given the array:

```java
byte[] data = {0x00, 0x0F, 0x10, 0x7F, (byte) 0x80, (byte) 0xFF};
```

Do the following:

1. Use `HexFormat.of().formatHex(data)` to produce the default hex string.
2. Use an uppercase formatter to produce a second string.
3. Explain why `0x0F` must have two digits and why `0xFF` can correspond to a `byte` with value `-1`.

### Exercise 2 — Formatting a Packet

Given a byte array containing a header and payload, create a formatter that displays bytes in the pattern `0x01:0x02:0x03`, uppercase. Format only the payload region, skipping the first two header bytes and the trailing one-byte checksum.

### Exercise 3 — Parsing a Hex String

Parse the string `48656c6c6f` into a byte array and decode it with `StandardCharsets.UTF_8`. Print `Hello`. Try replacing the string with `48656c6c6g` and explain the exception.

### Exercise 4 — Prefix and Delimiter

Create a formatter with prefix `0x`, a single-space delimiter, and uppercase. Format `{0x0A, 0x2B, 0x7F}`. Then use the same formatter to parse the generated string and verify that the two byte arrays are equal.

### Exercise 5 — Distinguishing Hex and Charset

Encode `"Xin chào"` using UTF-8, format the bytes as hex, then parse and decode back. Explain why a Vietnamese character can occupy more than one byte.

### Exercise 6 — Endianness Analysis

Given the byte array `{0x01, 0x02, 0x03, 0x04}`, print it in hex using `HexFormat`, then explain why its interpretation as a 32-bit integer can differ between big-endian and little-endian even though the hex string is unchanged.

## 16. Official Java 17 Documentation

- [Java SE 17 API — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): method list, formatter configuration, byte formatting/parsing, and slice handling.
- [Java SE 17 API — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): text conversion and manipulation methods.
- [Java SE 17 API — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): standard charsets such as UTF-8.
- [Java SE 17 API — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): reading and interpreting multi-byte data with a specific byte order.

`HexFormat` is suitable when you need a standardized way to **convert bytes to hex text and parse hex text back into bytes**. When processing text, always determine the charset before converting to bytes; when processing packets, always keep the byte order and protocol structure explicit. Hex helps inspect and exchange data representations, without deciding the meaning or protecting the data itself.
