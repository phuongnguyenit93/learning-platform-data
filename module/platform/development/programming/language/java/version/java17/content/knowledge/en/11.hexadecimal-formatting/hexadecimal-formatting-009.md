# Displaying Hashes and Binary Data for Diagnostics in Java 17

**Topic:** Java 17  
**Chapter:** Hexadecimal Data  
**Lesson:** Displaying Hashes and Binary Data for Diagnostics

When investigating data-related bugs, text logs are sometimes insufficient to tell exactly which bytes were produced, sent, or received. A byte may be a control character, a non-ASCII byte, a negative number when viewed through Java's `byte` type, or part of a binary structure. Displaying data in **hexadecimal (base 16)** makes each byte clear and compact to inspect.

In Java 17, the `java.util.HexFormat` API provides a standard way to format binary data into hex strings and parse them back. Combined with `hashCode()`, `Arrays.hashCode()`, `System.identityHashCode()`, and `MessageDigest`, you can produce diagnostic output to compare objects, inspect contents, and trace data.

Three kinds of information must be distinguished:

- **Object hash code (`hashCode`):** an `int` value used by hash-based structures like `HashMap`/`HashSet`; not a unique identifier.
- **Hex representation of binary data:** writing each byte as two base-16 digits; reversible back to bytes.
- **Cryptographic digests** such as SHA-256: hash outputs designed for integrity checking or cryptographic applications under the corresponding algorithm; distinct from `hashCode()`.

The examples below use stable Java 17 APIs, notably `HexFormat` introduced in Java 17. No preview features need to be enabled.

## 1. Why Display Data in Hex?

A byte has 8 bits, giving 256 distinct bit patterns. Hexadecimal uses 16 symbols: `0`–`9` and `A`–`F`. Each hex digit represents 4 bits (*nibble*), so **one byte is always represented by two hex digits**.

| Representation | Example of one byte | Length |
|---|---|---:|
| Binary | `11001010` | 8 bits |
| Hex | `CA` | 2 digits |
| Unsigned decimal | `202` | 1–3 digits |
| ASCII character (if printable) | No fixed mapping for every byte | Depends on encoding |

Example byte `0xCA`:

```text
Hex:       CA
Binary:    11001010
Unsigned:  202
```

Hex has several advantages for diagnostics:

- Shorter than binary: 2 characters instead of 8 characters per byte.
- Preserves every byte, regardless of whether the byte is a printable character.
- Easy to compare against packet captures, hexdumps, protocol specs, and output from system tools.
- Reversible back to the exact original byte array if formatted and parsed consistently.

### 1.1. Why Not Print a `byte[]` Array Directly?

```java
byte[] data = {0x41, 0x42, 0x43};

System.out.println(data);
```

The output typically looks like a class name and object identifier such as:

```text
[B@...
```

This is not the array contents. `System.out.println(data)` invokes the array's default object representation rather than printing individual bytes.

To inspect the contents, you must format the array:

```java
import java.util.Arrays;

byte[] data = {0x41, 0x42, 0x43};

System.out.println(Arrays.toString(data)); // [65, 66, 67]
```

`Arrays.toString(byte[])` displays values as signed `byte`s, so it is not hex format. For diagnosing binary data, `HexFormat` is usually a better fit.

## 2. The `HexFormat` API in Java 17

`java.util.HexFormat` is an immutable utility class for formatting bytes as hex and parsing hex strings back into bytes. You can obtain the default instance with `HexFormat.of()` or configure a delimiter, letter case, prefix, and suffix.

Import:

```java
import java.util.HexFormat;
```

Minimal example:

```java
byte[] bytes = {(byte) 0xCA, (byte) 0xFE, 0x00, 0x7F};

String hex = HexFormat.of().formatHex(bytes);

System.out.println(hex); // cafe007f
```

Each byte is converted into two lowercase hex digits in the default configuration.

### 2.1. Uppercase Formatting and Adding Delimiters

```java
byte[] packet = {
        (byte) 0xCA,
        (byte) 0xFE,
        0x00,
        0x7F,
        (byte) 0x80,
        (byte) 0xFF
};

HexFormat compact = HexFormat.of();
HexFormat spaced = HexFormat.ofDelimiter(" ");
HexFormat colonUpper = HexFormat.ofDelimiter(":").withUpperCase();

System.out.println(compact.formatHex(packet));
System.out.println(spaced.formatHex(packet));
System.out.println(colonUpper.formatHex(packet));
```

Output:

```text
cafe007f80ff
ca fe 00 7f 80 ff
CA:FE:00:7F:80:FF
```

Choosing a format:

- No delimiter: suitable for storing or transmitting contiguous hex strings.
- Space: easy to read in logs or dumps.
- Colon: familiar from MAC addresses or packet analysis tools.
- Uppercase or lowercase is purely a presentation convention; byte values do not change.

### 2.2. Commonly Used Methods

| Method | Purpose |
|---|---|
| `HexFormat.of()` | Gets the default configuration |
| `HexFormat.ofDelimiter(String)` | Creates a configuration with a separator between bytes |
| `withUpperCase()` | Formats hex letters in uppercase |
| `withLowerCase()` | Formats hex letters in lowercase |
| `withPrefix(String)` | Adds a configured prefix |
| `withSuffix(String)` | Adds a configured suffix |
| `formatHex(byte[])` | Formats the entire byte array |
| `formatHex(byte[], int, int)` | Formats a slice of the array |
| `parseHex(CharSequence)` | Parses a hex string into bytes |
| `toHexDigits(byte)` | Formats a byte as two hex digits |
| `toHexDigits(int)` | Formats an `int` as eight hex digits |

The `with...` methods return a new `HexFormat` configuration. They do not mutate the state of the current formatter.

### 2.3. Formatting Part of an Array

You can display only a slice of bytes:

```java
byte[] data = {
        0x10, 0x20, 0x30, 0x40, 0x50, 0x60
};

String middle = HexFormat.of().formatHex(data, 2, 5);

System.out.println(middle); // 304050
```

The index range is `[fromIndex, toIndex)`: start index inclusive, end index exclusive. This matches standard slicing conventions in Java.

## 3. Converting Hex Back to `byte[]`

A major benefit of `HexFormat` is the ability to parse hex data back into bytes:

```java
import java.util.HexFormat;
import java.util.Arrays;

public class HexParseExample {
    public static void main(String[] args) {
        String hex = "cafe007f80ff";

        byte[] bytes = HexFormat.of().parseHex(hex);

        System.out.println(Arrays.toString(bytes));
        System.out.println(HexFormat.of().formatHex(bytes));
    }
}
```

Output:

```text
[-54, -2, 0, 127, -128, -1]
cafe007f80ff
```

Negative numbers appear because Java's `byte` is an 8-bit signed integer type ranging from `-128` to `127`. The bit pattern of `0xCA` is still `11001010`; the signed value of that byte is `-54`.

### 3.1. Using a Delimited Formatter When Parsing

If the string has a delimiter, use the matching formatter:

```java
HexFormat format = HexFormat.ofDelimiter(":");

byte[] bytes = format.parseHex("CA:FE:00:7F");

System.out.println(HexFormat.of().formatHex(bytes));
// cafe007f
```

The formatter is configured with the delimiter to recognize the exact separation format. Avoid arbitrarily stripping characters before parsing, as that can mask data errors or change the string's meaning.

### 3.2. Handling Invalid Hex Strings

A hex string must have the valid digit count for each byte and contain only supported hex characters and the configured delimiter. Invalid strings throw `IllegalArgumentException`.

```java
try {
    byte[] bytes = HexFormat.of().parseHex("12G4");
} catch (IllegalArgumentException exception) {
    System.out.println("Invalid hex string");
}
```

Common errors:

- Contains characters outside `0`–`9`, `a`–`f`, `A`–`F`.
- Odd number of hex digits when the format has no special prefix/delimiter.
- Delimiter does not match the formatter configuration.
- Truncated data.

Do not swallow parse errors and substitute an empty array; record the cause so you know where the input data went wrong.

## 4. Signed `byte` and Reading Bytes as Unsigned

Java has no `ubyte` primitive type. The `byte` type represents an 8-bit signed integer:

```java
byte a = 127;
byte b = (byte) 0x80;
byte c = (byte) 0xFF;

System.out.println(a); // 127
System.out.println(b); // -128
System.out.println(c); // -1
```

Meanwhile, when analyzing packets or files, we often want to read the bit pattern as an unsigned number from 0 to 255.

Use `Byte.toUnsignedInt(byte)`:

```java
byte value = (byte) 0xFF;

int signed = value;
int unsigned = Byte.toUnsignedInt(value);

System.out.println(signed);   // -1
System.out.println(unsigned); // 255
```

### 4.1. Why Is `HexFormat` Useful with Negative Bytes?

`HexFormat.formatHex(byte[])` formats the exact 8-bit pattern of each element. It does not print a minus sign or sign-extend to 32 bits.

```java
byte value = (byte) 0xFF;

System.out.println(value); // -1
System.out.println(HexFormat.of().formatHex(new byte[]{value})); // ff
```

If you widen `byte` to `int` yourself and call `Integer.toHexString`, sign extension can occur:

```java
byte value = (byte) 0xFF;

System.out.println(Integer.toHexString(value)); // ffffffff
System.out.println(Integer.toHexString(value & 0xFF)); // ff
```

The expression `value & 0xFF` keeps the low 8 bits, mapping the bit pattern to the unsigned integer range 0–255. However, when formatting an entire byte array, use `HexFormat` directly.

## 5. Displaying Data in 8-Bit Binary Form

Hex is compact, but when you need to inspect individual bits — such as protocol flags, bit masks, or headers — you can convert each byte into a binary string.

`Integer.toBinaryString(int)` returns a binary representation without leading zeros. To ensure every byte always has 8 bits, pad with zeros.

```java
static String toBinaryString(byte value) {
    int unsigned = Byte.toUnsignedInt(value);
    String bits = Integer.toBinaryString(unsigned);
    return "0".repeat(8 - bits.length()) + bits;
}
```

Example:

```java
byte[] data = {(byte) 0x03, (byte) 0x80, (byte) 0xFF};

for (byte value : data) {
    System.out.println(toBinaryString(value));
}
```

Output:

```text
00000011
10000000
11111111
```

Each line always displays all 8 bits of one byte.

### 5.1. Printing Both Hex and Binary Side by Side

```java
byte[] data = {(byte) 0x03, (byte) 0x80, (byte) 0xFF};

for (byte value : data) {
    String hex = HexFormat.of().toHexDigits(value);
    String binary = toBinaryString(value);

    System.out.printf("hex=%s binary=%s%n", hex, binary);
}
```

Output:

```text
hex=03 binary=00000011
hex=80 binary=10000000
hex=ff binary=11111111
```

When analyzing bit flags, you can immediately see whether the highest bit is set. For example, `0x80` corresponds to `10000000`, meaning bit 7 is set while all other bits are cleared.

### 5.2. Formatting the Bits of an `int`

An `int` has 32 bits. `Integer.toBinaryString(value)` omits leading zeros, so you can write a helper:

```java
static String to32BitBinary(int value) {
    String bits = Integer.toBinaryString(value);
    return "0".repeat(32 - bits.length()) + bits;
}
```

For the value `5`, the output is:

```text
00000000000000000000000000000101
```

For negative numbers, `Integer.toBinaryString` returns the full 32-bit two's complement representation. Padding keeps the string at length 32.

## 6. Displaying Object Hash Codes in Hex

`hashCode()` returns a 32-bit `int`. For compact logging and easy comparison, you can display that bit pattern as eight hex digits.

```java
import java.util.HexFormat;

static String hexHash(int hash) {
    return "0x" + HexFormat.of().toHexDigits(hash);
}
```

Example:

```java
String text = "Java 17";

int hash = text.hashCode();

System.out.println(hash);
System.out.println("0x" + HexFormat.of().toHexDigits(hash));
```

`toHexDigits(int)` formats an `int` into eight hex digits, even when the value is negative. For instance, `-1` has a 32-bit pattern of all `1`s, so its hex form is `ffffffff`.

### 6.1. A Hash Code Is Not a Unique ID

According to the contract of `Object.hashCode()`:

- If two objects are equal according to `equals()`, they must have the same hash code.
- Two unequal objects **can still** have the same hash code (*collision*).
- Hash codes must remain consistent within a single execution as long as information used in `equals()` does not change.
- There is no general guarantee that hash codes of arbitrary object types are stable across different program runs.

Therefore, do not use hash codes to:

- Serve as a unique primary key for records.
- Uniquely identify an object in the system.
- Verify cryptographic integrity of files.
- Generate security tokens.
- Store as long-term IDs across application versions.

Hash codes primarily serve hash-based data structures.

### 6.2. Distinguishing `hashCode()` and `System.identityHashCode()`

A class may override `hashCode()` to reflect logical content. `System.identityHashCode(object)` returns the object's identity hash code, regardless of any overridden `hashCode()` implementation.

```java
record User(String name, int age) {}

User first = new User("An", 20);
User second = new User("An", 20);

System.out.println(first.equals(second)); // true
System.out.println(first.hashCode() == second.hashCode()); // true

System.out.println(System.identityHashCode(first));
System.out.println(System.identityHashCode(second));
```

The two records have equal content, so `equals()` and `hashCode()` match. However, they are two distinct instances. Their identity hash codes are usually different, yet **they can still collide** because an identity hash code is also a finite integer.

`identityHashCode` is not a memory address and is not guaranteed to be unique.

### 6.3. Formatting a Hash Code as Hex

```java
static String formatHash(Object value) {
    if (value == null) {
        return "null";
    }

    int hash = value.hashCode();
    return "0x" + HexFormat.of().toHexDigits(hash);
}
```

The eight-digit form keeps logs consistent:

```text
hash=0x0000002a
hash=0x89abcdef
hash=0xffffffff
```

Leading zeros do not change the value. They simply make it clear that this is the full 32-bit representation.

## 7. Hashing Array and Object Contents

### 7.1. Java Arrays Do Not Hash by Content by Default

An array is an object. Calling `hashCode()` directly on an array normally uses identity hashing, not a hash of the bytes inside.

```java
byte[] first = {1, 2, 3};
byte[] second = {1, 2, 3};

System.out.println(first.equals(second)); // false
System.out.println(first.hashCode() == second.hashCode()); // usually false
```

To compute a hash based on array contents, use `Arrays.hashCode`:

```java
import java.util.Arrays;

byte[] first = {1, 2, 3};
byte[] second = {1, 2, 3};

System.out.println(Arrays.equals(first, second)); // true
System.out.println(Arrays.hashCode(first) == Arrays.hashCode(second)); // true
```

`Arrays.hashCode(byte[])` is a 32-bit hash code computed over the byte contents. Two arrays with identical contents will have the same hash code, though two arrays with different contents can still collide.

### 7.2. Displaying a Content Hash in Hex

```java
byte[] payload = {(byte) 0xCA, (byte) 0xFE, 0x01};

int contentHash = Arrays.hashCode(payload);

System.out.println("payload=" + HexFormat.of().formatHex(payload));
System.out.println("hash=0x" + HexFormat.of().toHexDigits(contentHash));
```

The two log lines answer two different questions:

- `payload=...` shows the exact bytes present in the data.
- `hash=...` is a 32-bit summary value for quick comparison in hash structures.

Do not use a 32-bit content hash to conclude with certainty that two payloads are identical. When content verification is needed, compare bytes directly with `Arrays.equals`.

### 7.3. Using `Objects.hash()` for Multiple Fields

For regular objects, you can combine hashes from multiple fields:

```java
import java.util.Objects;

final class Customer {
    private final long id;
    private final String name;

    Customer(long id, String name) {
        this.id = id;
        this.name = name;
    }

    @Override
    public int hashCode() {
        return Objects.hash(id, name);
    }
}
```

When overriding `hashCode()`, uphold the contract with `equals()`: if two objects are considered equal, their hash codes must be equal.

For primitive arrays such as `byte[]`, use `Arrays.hashCode(bytes)` to hash the contents. Do not rely on `Objects.hash(bytes)` to hash individual bytes of a primitive array.

## 8. Hex Dump: Displaying Offset, Hex, and Readable Characters

A diagnostic log for binary data is often more useful when it includes:

- Offset: the byte position within the data.
- Hex: the value of each byte.
- ASCII/printable: printable characters, if the bytes fall within the appropriate range.

Data example:

```text
Offset   Hex bytes                 ASCII
0000     48 65 6c 6c 6f 20 4a 61   Hello Ja
0008     76 61 20 31 37            va 17
```

A hex dump helps spot truncated data, extra bytes, control bytes, or encoding mismatches. For general binary data, the ASCII column is only a secondary view; non-printable bytes can be replaced with dots.

### 8.1. Simple Dump Function in Java 17

```java
import java.util.HexFormat;
import java.nio.charset.StandardCharsets;

public class HexDump {
    private static final HexFormat HEX = HexFormat.ofDelimiter(" ");

    static void dump(byte[] data, int bytesPerLine) {
        for (int offset = 0; offset < data.length; offset += bytesPerLine) {
            int end = Math.min(offset + bytesPerLine, data.length);

            String hex = HEX.formatHex(data, offset, end);

            StringBuilder ascii = new StringBuilder();
            for (int i = offset; i < end; i++) {
                int value = Byte.toUnsignedInt(data[i]);

                if (value >= 32 && value <= 126) {
                    ascii.append((char) value);
                } else {
                    ascii.append('.');
                }
            }

            System.out.printf(
                    "%08X  %-47s  %s%n",
                    offset,
                    hex,
                    ascii
            );
        }
    }

    public static void main(String[] args) {
        byte[] data = "Hello Java 17".getBytes(StandardCharsets.US_ASCII);
        dump(data, 8);
    }
}
```

Output:

```text
00000000  48 65 6c 6c 6f 20 4a 61                        Hello Ja
00000008  76 61 20 31 37                                 va 17
```

This function serves as a diagnostic illustration:

- The offset is printed as 8 hex digits.
- Each byte is printed as two digits.
- ASCII displays only the byte range 32–126; other bytes become `.`.
- A shorter final line is handled via `Math.min`.

In production tools, you can add a maximum byte display limit, paginate data, display total size, and avoid printing sensitive contents.

### 8.2. Offset Is Not a Memory Address

The offset `00000008` means the byte shown is at index 8 from the start of the array (zero-based). It is not a RAM address or an absolute file address.

If dumping a slice that starts at an outer offset within a larger array, add the base position of the slice to the internal index to display the global offset.

## 9. Binary Data and Character Encoding

A `byte[]` does not inherently carry information stating whether it is UTF-8, UTF-16, a PNG image, or a protocol packet. Hex only shows the bytes; interpreting them as text requires knowing the encoding.

### 9.1. Converting a String to Bytes Using an Explicit Charset

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String message = "Xin chào Java 17";

byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
String hex = HexFormat.of().formatHex(bytes);

System.out.println(hex);
```

UTF-8 can use multiple bytes per character. Therefore, the byte count does not necessarily equal the number of characters in the string.

### 9.2. Restoring a String from Bytes

```java
byte[] bytes = HexFormat.of().parseHex(hex);

String restored = new String(bytes, StandardCharsets.UTF_8);

System.out.println(restored);
```

Use the same charset when converting back. Avoid `new String(bytes)` or parameterless `getBytes()` in code needing consistent results, because they depend on the environment's default charset.

### 9.3. Hex Is Not an Encoding

Terms to distinguish:

| Concept | Role |
|---|---|
| Byte | 8-bit unit of data |
| Binary | Representation of bits using 0 and 1 |
| Hexadecimal | Representation of bits using base-16 digits |
| UTF-8 | Rules for encoding characters into bytes |
| ASCII | Basic character code set |
| Hex dump | Presentation of bytes in hex, often with offsets and characters |

A hex string of UTF-8 is a **text representation of the UTF-8 bytes**, not a new charset.

## 10. Distinguishing Hash Codes from Cryptographic Digests

`hashCode()` returns a 32-bit `int` to support Java hash collections. It is not designed to resist intentional collisions or guarantee data integrity.

If you need a stronger fingerprint for data, you can use `MessageDigest`, such as SHA-256:

```java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.nio.charset.StandardCharsets;

public class DigestExample {
    public static void main(String[] args) throws NoSuchAlgorithmException {
        byte[] data = "Java 17".getBytes(StandardCharsets.UTF_8);

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] result = digest.digest(data);

        System.out.println(HexFormat.of().formatHex(result));
    }
}
```

SHA-256 produces a 256-bit digest, typically displayed as 64 hex digits. This representation is commonly used when logging checksums or data fingerprints.

### 10.1. Comparing the Three Concepts

| Characteristic | `Object.hashCode()` | `Arrays.hashCode(byte[])` | SHA-256 |
|---|---|---|---|
| Result | 32-bit `int` | 32-bit `int` | 256-bit digest |
| Primary goal | Hash collections | Hashing array contents in Java | Cryptographic fingerprint |
| Collisions | Can occur | Can occur | Theoretically possible, but practically infeasible to find collisions |
| Use as unique ID | No | No | Should not be treated as an absolute unique ID |
| Integrity checking | Unsuitable | Unsuitable | Suitable for detecting data changes under a digest model |
| Tamper resistance | No | No | A plain digest does not authenticate origin; use HMAC or signatures when authentication is needed |

A plain SHA-256 digest does not prove who created the data. If you need to verify that data came from a party holding a secret key, use HMAC or digital signatures in an appropriate security design.

## 11. Comprehensive Example: Diagnosing a Payload

A diagnostic utility often needs to display simultaneously:

- Payload size.
- Hex data.
- Content hash.
- SHA-256 digest.
- The first few bytes in binary.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HexFormat;

public class PayloadDiagnostics {

    private static final HexFormat HEX = HexFormat.of();

    static String bits(byte value) {
        int unsigned = Byte.toUnsignedInt(value);
        String binary = Integer.toBinaryString(unsigned);
        return "0".repeat(8 - binary.length()) + binary;
    }

    static void print(byte[] payload) throws NoSuchAlgorithmException {
        int contentHash = Arrays.hashCode(payload);

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(payload);

        System.out.println("length=" + payload.length);
        System.out.println("hex=" + HEX.formatHex(payload));
        System.out.println(
                "contentHash=0x" + HEX.toHexDigits(contentHash)
        );
        System.out.println("sha256=" + HEX.formatHex(digest));

        int previewLength = Math.min(payload.length, 8);
        for (int i = 0; i < previewLength; i++) {
            System.out.printf(
                    "byte[%d] hex=%s binary=%s%n",
                    i,
                    HEX.toHexDigits(payload[i]),
                    bits(payload[i])
            );
        }
    }

    public static void main(String[] args) throws NoSuchAlgorithmException {
        byte[] payload =
                "Java 17 diagnostic".getBytes(StandardCharsets.UTF_8);

        print(payload);
    }
}
```

The printed SHA-256 value will be deterministic for the same input byte sequence. The content hash is also deterministic within Java, though it is only 32 bits and subject to collisions. The hex dump shows the actual bytes, helping inspect encoding or pinpoint where data changed.

## 12. Common Mistakes When Displaying Hashes and Binary Data

### Mistake 1. Printing `byte[]` Directly

```java
System.out.println(bytes);
```

This prints the object identifier form, not the contents. Use `HexFormat.of().formatHex(bytes)` or `Arrays.toString(bytes)` depending on your goal.

### Mistake 2. Confusing Negative Bytes with Corrupt Data

```java
byte value = (byte) 0xFF;
System.out.println(value); // -1
```

This is the signed representation of the same `11111111` bit pattern. Use `Byte.toUnsignedInt(value)` if you want 255, or `HexFormat` if you want hex `ff`.

### Mistake 3. Widening Negative Bytes to int and Formatting Without Masking

```java
byte value = (byte) 0x80;

System.out.println(Integer.toHexString(value)); // ffffff80
```

This is sign extension to 32 bits. Use `HexFormat.of().toHexDigits(value)` or `value & 0xFF` if formatting with integer APIs.

### Mistake 4. Using `hashCode()` as a Security Fingerprint

A 32-bit hash code can collide and has no resistance to attacks. Use `MessageDigest` with a suitable algorithm when a digest is required.

### Mistake 5. Assuming Two Objects with the Same Hash Code Are Equal

Two different objects can have the same hash code. Always check `equals()` or compare the concrete data.

### Mistake 6. Using Array `hashCode()` to Compare Contents

Arrays do not override `equals()`/`hashCode()` by content. Use `Arrays.equals()` and `Arrays.hashCode()`.

### Mistake 7. Using the Default Charset

`new String(bytes)` and `text.getBytes()` can produce different results across environments. Specify `StandardCharsets.UTF_8` or the charset required by the protocol.

### Mistake 8. Parsing Hex with a Formatter Having the Wrong Delimiter

If logs use `:` between bytes, parse with `HexFormat.ofDelimiter(":")`. Do not arbitrarily strip delimiters if format validation is needed.

### Mistake 9. Assuming a Hex Dump Is Raw Data

A hex dump is a **presentation** of data. When copying from logs, prefixes, delimiters, offsets, or ASCII columns may be included. When parsing back, pass only the valid hex byte section to the formatter.

### Mistake 10. Logging Entire Sensitive Payloads

Payloads may contain personal information, tokens, keys, authentication data, or business content. Diagnostic tools should cap lengths, mask sensitive fields, and enable verbose logging only for legitimate operational reasons.

## 13. Data Diagnostics Workflow Using Hex

When two systems produce different data, you can follow this sequence:

1. **Check sizes:** do the two payloads have the same byte count?
2. **Display hex:** use `HexFormat` to identify the first differing byte.
3. **Check encoding:** if the payload is text, determine whether it is UTF-8 or another charset.
4. **Inspect binary:** when analyzing bit flags, header bytes, or masks.
5. **Compare contents:** use `Arrays.equals()` rather than comparing hash codes alone.
6. **Compute a digest:** use SHA-256 to compare fingerprints of large payloads or across systems.
7. **Record context:** offset, length, charset, delimiter, and capture timestamp.

Example finding the first differing position:

```java
static int firstDifference(byte[] left, byte[] right) {
    int commonLength = Math.min(left.length, right.length);

    for (int i = 0; i < commonLength; i++) {
        if (left[i] != right[i]) {
            return i;
        }
    }

    return left.length == right.length ? -1 : commonLength;
}
```

If `-1` is returned, the two arrays are identical. If a non-negative index is returned, it is the position of the first differing byte or the index where one array ends before the other.

You can display the region around that position:

```java
int difference = firstDifference(left, right);

if (difference >= 0) {
    int from = Math.max(0, difference - 4);
    int leftTo = Math.min(left.length, difference + 5);
    int rightTo = Math.min(right.length, difference + 5);

    System.out.println("left:  " + HexFormat.ofDelimiter(" ")
            .formatHex(left, from, leftTo));
    System.out.println("right: " + HexFormat.ofDelimiter(" ")
            .formatHex(right, from, rightTo));
}
```

In real applications, if the two arrays have different lengths, adjust `from` appropriately for each array before calling `formatHex`; the example above assumes the starting index is valid for both.

## 14. Self-Practice Exercises

### Exercise 1. Converting Bytes to Hex

Given:

```java
byte[] values = {0, 15, 16, 127, (byte) 128, (byte) 255};
```

**Question:** What does `HexFormat.of().formatHex(values)` return?

**Answer:** `000f107f80ff`. Each byte has two hex digits, including leading zeros.

### Exercise 2. Explaining Negative Numbers

Given:

```java
byte value = (byte) 0xFF;
System.out.println(value);
System.out.println(Byte.toUnsignedInt(value));
```

**Answer:** The first line prints `-1`; the second line prints `255`. The bit pattern remains `11111111`.

### Exercise 3. Choosing the Right Hash for Arrays

Given two byte arrays with identical contents, should you use `first.hashCode()` or `Arrays.hashCode(first)` to hash by content?

**Answer:** `Arrays.hashCode(first)`. Java arrays do not hash by content when calling `hashCode()` directly.

### Exercise 4. Distinguishing Collisions

Two distinct objects have the same `hashCode()`. Can you conclude they are equal?

**Answer:** No. Matching hash codes are merely a collision; `equals()` is needed to test equality per class logic.

### Exercise 5. Choosing an API for Payloads

You need to log a binary payload and accurately convert it back to bytes after copying from the log. What should you use?

**Answer:** `HexFormat` with a clear delimiter convention, then parse back using the matching formatter. Remove any offset and ASCII columns from the string before passing it to the parser.

### Exercise 6. Hash Code or SHA-256?

A system needs a payload fingerprint for comparison between two servers. Should you choose `Arrays.hashCode()` or SHA-256?

**Answer:** SHA-256 is better suited for data fingerprinting because the digest is long and has cryptographic properties. `Arrays.hashCode()` is only a 32-bit hash for Java data structures, collides more often, and is not designed for collision resistance.

### Exercise 7. Why Specify the Charset?

A string with Vietnamese diacritics is converted to bytes on two different environments. Why might the hex differ?

**Answer:** If the default charset is used, each environment may encode differently. Use `getBytes(StandardCharsets.UTF_8)` to produce consistent bytes.

## 15. Official References

- [JDK 17 API — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): formatting and parsing byte data as hex, delimiters, case, and per-byte conversions.
- [JDK 17 API — Object.hashCode()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()): the Java object hash code contract.
- [JDK 17 API — System.identityHashCode(Object)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object)): object identity hash code.
- [JDK 17 API — Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): `equals`, `hashCode`, `deepHashCode`, and array utilities.
- [JDK 17 API — Byte](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html): signed/unsigned conversions and byte utilities.
- [JDK 17 API — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): cryptographic digest APIs such as SHA-256.

**Takeaway:** Use `HexFormat` to display and recover bytes; use `Byte.toUnsignedInt` when reading bytes in the 0–255 range; use `Arrays.hashCode` for array content hashing; use `hashCode()` for object hash structures; and choose a digest like SHA-256 when you need a data fingerprint. Hex is a presentation of bit patterns and does not alter or encrypt the underlying content.
