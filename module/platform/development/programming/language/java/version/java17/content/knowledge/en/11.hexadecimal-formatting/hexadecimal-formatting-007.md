# Slice Bounds and Length Validation in Hexadecimal Processing (Java 17)

When representing bytes in hexadecimal, each byte is typically written as two hex digits. For example, three bytes with values `0x12`, `0xA0`, and `0xFF` are represented as the string `12a0ff`. This representation is easy to read and convenient for logging, exchanging data, or inspecting binary content.

However, when processing only part of the data, you must clearly distinguish the **hex character string length** from the **actual byte count**. At the same time, every slicing operation must validate start index, length, and data bounds before reading or decoding.

In Java 17, `java.util.HexFormat` provides the standard API for formatting and parsing hex strings. Combined with `Objects.checkFromIndexSize`, you can process byte slices according to clear rules, avoiding out-of-bounds errors, *off-by-one* mistakes, and integer overflow when computing `offset + length`.

## 1. Length of Hex Data and Byte Data

One byte has 8 bits, which can be represented by two hexadecimal digits. Each hex digit represents 4 bits:

| Data | Value | Hex representation |
| --- | ---: | --- |
| 1 byte | `0x2A` | `2a` |
| 2 bytes | `0x12 0xA0` | `12a0` |
| 4 bytes | `0xDE 0xAD 0xBE 0xEF` | `deadbeef` |

For a hex string without delimiters, prefixes, or whitespace:

\[
\text{hexCharacterCount} = 2 \times \text{byteCount}
\]

and:

\[
\text{byteCount} = \frac{\text{hexCharacterCount}}{2}
\]

Therefore:

- 2 hex characters correspond to 1 byte.
- 32 hex characters correspond to 16 bytes.
- 64 hex characters correspond to 32 bytes.
- A string with an odd character count cannot represent a complete byte sequence in the two-characters-per-byte format.

Example:

```java
String hex = "12a0ff";
System.out.println(hex.length());       // 6 characters
System.out.println(hex.length() / 2);   // 3 bytes
```

Do not treat `hex.length()` as the byte count. If an application receives a length field declared in bytes, convert units explicitly and validate before processing.

### 1.1. When Delimiters or Prefixes Are Present

The string length is no longer always twice the byte count if the format adds extra characters:

```java
import java.util.HexFormat;

byte[] data = {0x12, (byte) 0xA0, (byte) 0xFF};

System.out.println(HexFormat.of().formatHex(data));
// 12a0ff

System.out.println(HexFormat.ofDelimiter(":").formatHex(data));
// 12:a0:ff
```

With the string `12:a0:ff`, there are 8 displayed characters, yet still only 3 bytes. If delimiters, prefixes, or suffixes are added, you cannot apply `length / 2` directly to the whole string.

Determine the input format first:

- Contiguous hex: two characters per byte.
- Delimited hex: character count also depends on the delimiter.
- Prefixed hex such as `0x`: prefix rules must be accounted for.
- Hex strings with spaces or line breaks: explicitly specify whether they are allowed; do not blindly strip characters because that can mask malformed data.

## 2. Using HexFormat in Java 17

`HexFormat` is a standard API in `java.util`, available since Java 17. It supports converting bytes to hex strings, parsing hex strings to bytes, and operating on an index range of data.

### 2.1. Converting a Byte Array to a Hex String

```java
import java.util.HexFormat;

public class FormatHexDemo {
    public static void main(String[] args) {
        byte[] data = {0x12, (byte) 0xA0, (byte) 0xFF};

        String hex = HexFormat.of().formatHex(data);
        System.out.println(hex); // 12a0ff
    }
}
```

Java's `byte` is a signed type, but `HexFormat` formats the byte's bit pattern into two hex digits. When writing literals greater than 127, cast them as `(byte) 0xA0`.

### 2.2. Parsing a Hex String into a Byte Array

```java
import java.util.HexFormat;

public class ParseHexDemo {
    public static void main(String[] args) {
        byte[] data = HexFormat.of().parseHex("12a0ff");

        for (byte value : data) {
            System.out.printf("%02x ", value & 0xff);
        }
    }
}
```

Output:

```text
12 a0 ff
```

`parseHex` validates characters against the hex format and returns a byte array. Strings with invalid characters or an invalid digit count are rejected with `IllegalArgumentException`.

### 2.3. Choosing Uppercase and Delimiters

```java
import java.util.HexFormat;

byte[] data = {0x01, 0x23, (byte) 0xAB};

String lower = HexFormat.of().formatHex(data);
String upper = HexFormat.of().withUpperCase().formatHex(data);
String separated = HexFormat.ofDelimiter(":").formatHex(data);

System.out.println(lower);     // 0123ab
System.out.println(upper);     // 0123AB
System.out.println(separated); // 01:23:ab
```

Uppercase and lowercase are both valid ways of writing hex digits. When comparing strings, standardize the format or compare bytes after parsing instead of comparing unnormalized text.

## 3. Slice Conventions: offset, length, and end index

When processing part of a byte array, there are typically three quantities:

- `offset`: starting position.
- `length`: number of bytes to take.
- `end`: ending position under the *exclusive* convention.

Relationship:

\[
end = offset + length
\]

The range `[offset, end)` includes `offset` and excludes `end`.

Array example:

```text
Index:  0    1    2    3    4    5
Data:  12   A0   FF   34   56   78
       |---------|
        [1, 4) = A0 FF 34
```

A slice starting at index 1 with length 3 includes the elements at indices 1, 2, and 3. The end index is 4, so the element at index 4 is not included.

A common way to phrase this in Java is:

`fromIndex` inclusive, `toIndex` exclusive.

Example:

```java
byte[] data = {
        0x12, (byte) 0xA0, (byte) 0xFF,
        0x34, 0x56, 0x78
};

int from = 1;
int to = 4;

for (int i = from; i < to; i++) {
    System.out.printf("%02x ", data[i] & 0xff);
}
```

The output is `a0 ff 34`.

Do not use `i <= to` in a loop for a `[from, to)` range, as that would access one extra element outside the slice.

## 4. Validating Byte Range Bounds Safely

Suppose you have an array `data` and need to take `length` bytes starting at `offset`. The validity conditions are:

1. `offset` is non-negative.
2. `length` is non-negative.
3. The requested region lies completely within the array.

A readable check looks like:

```java
if (offset < 0 || length < 0 || offset + length > data.length) {
    throw new IndexOutOfBoundsException("Invalid byte range");
}
```

However, the addition `offset + length` can **overflow `int`** if both values are large. When overflow occurs, the result can become negative or smaller than expected, causing the check to fail silently.

### 4.1. Using Objects.checkFromIndexSize

Java 17 provides `Objects.checkFromIndexSize(fromIndex, size, length)` to verify that the range `[fromIndex, fromIndex + size)` lies within bounds:

```java
import java.util.Objects;

static void validateRange(byte[] data, int offset, int length) {
    Objects.requireNonNull(data, "data");
    Objects.checkFromIndexSize(offset, length, data.length);
}
```

This method checks for negative indices, negative size, and out-of-bounds ranges, while performing the check in a way that avoids overflow when adding indices.

When invalid, the method throws `IndexOutOfBoundsException` (or a suitable subclass). You can let the standard exception propagate to the caller or translate it into an input error per your application's API contract.

### 4.2. Manual Overflow-Safe Validation

If you need to write custom validation logic, check signs first and then compare `offset` against the remaining capacity of the array:

```java
static void checkRange(byte[] data, int offset, int length) {
    if (data == null) {
        throw new NullPointerException("data");
    }
    if (offset < 0 || length < 0 || offset > data.length - length) {
        throw new IndexOutOfBoundsException("Invalid byte range");
    }
}
```

Once `length >= 0` is confirmed, `data.length - length` cannot overflow positive integers; if `length` exceeds the array length, the right-hand side becomes negative and the condition rejects the range.

In Java 17, `Objects.checkFromIndexSize` is usually the concise, less error-prone choice that directly expresses range validation.

## 5. Slicing Bytes and Formatting Directly with HexFormat

`HexFormat` has overloads accepting an index range. This lets you format a byte slice without creating a subarray:

```java
import java.util.HexFormat;
import java.util.Objects;

public class HexSegmentDemo {
    static String formatSegment(byte[] data, int offset, int length) {
        Objects.requireNonNull(data, "data");
        Objects.checkFromIndexSize(offset, length, data.length);

        return HexFormat.of().formatHex(data, offset, offset + length);
    }

    public static void main(String[] args) {
        byte[] data = {
                0x12, (byte) 0xA0, (byte) 0xFF,
                0x34, 0x56, 0x78
        };

        System.out.println(formatSegment(data, 1, 3)); // a0ff34
        System.out.println(formatSegment(data, 0, 2)); // 12a0
    }
}
```

The `formatHex(bytes, fromIndex, toIndex)` API uses inclusive `fromIndex` and exclusive `toIndex`. Once `Objects.checkFromIndexSize` verifies the range is valid, `offset + length` is guaranteed to be within the array's length.

### 5.1. Creating a Subarray When Ownership of Separate Data Is Needed

If you need to store or pass the byte slice separately, use `Arrays.copyOfRange`:

```java
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Objects;

static byte[] copySegment(byte[] data, int offset, int length) {
    Objects.requireNonNull(data, "data");
    Objects.checkFromIndexSize(offset, length, data.length);
    return Arrays.copyOfRange(data, offset, offset + length);
}

static String hexOfSegment(byte[] data, int offset, int length) {
    return HexFormat.of().formatHex(copySegment(data, offset, length));
}
```

Comparison:

| Approach | Characteristics |
| --- | --- |
| `HexFormat.formatHex(data, from, to)` | Formats the data slice directly; no subarray allocation needed. |
| `Arrays.copyOfRange(data, from, to)` | Creates a copy of the data; useful when an independent slice is needed or passed to another API. |
| `ByteBuffer` with an appropriate view | Can be used to read multiple fields by position without copying; requires careful position/limit management. |

If you only need to display a byte slice as hex, direct formatting is simpler. If you need to mutate or store the slice independently, creating a copy may be more appropriate.

## 6. Slicing a Segment from a Hex String

When a hex string has no delimiter, each byte occupies two characters. Thus, to extract the byte slice `[byteOffset, byteOffset + byteLength)`, the corresponding character positions in the string are:

\[
charFrom = 2 \times byteOffset
\]

\[
charTo = 2 \times (byteOffset + byteLength)
\]

Example with the string `12a0ff345678`:

```text
Hex character index:
0 1 2 3 4 5 6 7 8 9 10 11
1 2 a 0 f f 3 4 5 6  7  8

Byte index:
0   1   2   3   4   5
12  a0  ff  34  56  78

Take bytes [1, 4) = a0 ff 34
Take chars [2, 8) = a0ff34
```

### 6.1. Validating the Entire String Before Converting Byte Offset to Char Offset

Example method:

```java
import java.util.HexFormat;
import java.util.Objects;

static byte[] parseByteSegment(
        String hex,
        int byteOffset,
        int byteLength) {

    Objects.requireNonNull(hex, "hex");

    if ((hex.length() & 1) != 0) {
        throw new IllegalArgumentException(
                "Hex string must contain an even number of characters");
    }

    int byteCount = hex.length() / 2;
    Objects.checkFromIndexSize(byteOffset, byteLength, byteCount);

    int charFrom = byteOffset * 2;
    int charTo = (byteOffset + byteLength) * 2;

    return HexFormat.of().parseHex(hex, charFrom, charTo);
}
```

Because the string has been confirmed to have an even number of characters, `byteCount` is the number of represented bytes. After `checkFromIndexSize`, both `byteOffset + byteLength` and multiplying by 2 remain within the string's bounds, so the character index calculation cannot overflow `int`.

Example:

```java
byte[] segment = parseByteSegment("12a0ff345678", 1, 3);
System.out.println(HexFormat.of().formatHex(segment)); // a0ff34
```

### 6.2. Parsing Directly by Character Indices

If the caller already works with character indices rather than byte indices, `HexFormat` supports parsing a range of a `CharSequence`:

```java
String hex = "12a0ff345678";
byte[] segment = HexFormat.of().parseHex(hex, 2, 8);

System.out.println(HexFormat.of().formatHex(segment)); // a0ff34
```

Constraints:

- `fromIndex` and `toIndex` are character indices into the string.
- `toIndex` excludes the character at that position.
- The slice length must be even to represent complete bytes.
- Every character in the slice must be a valid hex digit.

If the input is a string sent by a user or external system, check an overall size limit before parsing to avoid unexpected array allocations.

## 7. Checking Input Length Before Parsing

Do not parse unbounded hex data first and check the byte size afterward. With large inputs, creating strings or byte arrays can consume excessive memory and time.

Example method accepting at most `maxBytes`:

```java
import java.util.HexFormat;
import java.util.Objects;

static byte[] parseHexWithLimit(String hex, int maxBytes) {
    Objects.requireNonNull(hex, "hex");

    if (maxBytes < 0) {
        throw new IllegalArgumentException("maxBytes must not be negative");
    }

    long maxHexChars = 2L * maxBytes;
    if (hex.length() > maxHexChars) {
        throw new IllegalArgumentException("Hex input is too long");
    }

    if ((hex.length() & 1) != 0) {
        throw new IllegalArgumentException("Hex input length must be even");
    }

    return HexFormat.of().parseHex(hex);
}
```

Using `long` for `2L * maxBytes` prevents `int` overflow. After the size check, `parseHex` validates the characters and constructs the byte array.

If an exact length is required, such as requiring the input to be exactly 16 bytes:

```java
static byte[] parseExactly(String hex, int expectedBytes) {
    Objects.requireNonNull(hex, "hex");

    if (expectedBytes < 0) {
        throw new IllegalArgumentException("expectedBytes must not be negative");
    }

    long expectedChars = 2L * expectedBytes;
    if (hex.length() != expectedChars) {
        throw new IllegalArgumentException(
                "Expected " + expectedBytes + " bytes");
    }

    return HexFormat.of().parseHex(hex);
}
```

For non-delimited input, checking the exact byte length also validates the required character count. `parseHex` then validates the character contents.

### 7.1. Bounding Before Reading Data from Network or Files

If a message includes a sender-supplied length field, do not trust that field immediately:

1. Read the fixed-size header.
2. Check that the declared length is non-negative and within the protocol limit.
3. Verify the length can be safely converted to an array or buffer size.
4. Only then allocate or read the payload.
5. Confirm the actual number of bytes received equals the requested byte count.

When reading from an `InputStream`, `read(byte[])` may return fewer bytes than requested. When full data is required, use `readNBytes(...)` and verify the actual byte count received, or `DataInputStream.readFully(...)` if the contract requires reading the full amount.

A declared length in a header is untrusted input. Validate business limits and resource limits before allocating memory.

## 8. Distinguishing String Length, Byte Count, and Indices

In hex processing, three different index systems can appear:

| Subject | Index/length unit | Example |
| --- | --- | --- |
| `byte[]` | Byte count | `data.length == 3` means 3 bytes. |
| Contiguous hex string | Hex character count | `hex.length() == 6` represents 3 bytes. |
| Java strings in general | UTF-16 code units (`char`) | `String.length()` counts char units, not UTF-8 bytes. |

For ASCII hex, each character is one UTF-16 `char` unit and two characters map to one byte. Do not apply division by two to an arbitrary UTF-8 text string. Text length and encoded byte length are two distinct concepts.

### 8.1. Do Not Take a Substring Using Byte Indices Directly

Semantically incorrect example:

```java
String hex = "12a0ff345678";

// Intended to take byte 1 through byte 3, but used char indices 1..4.
String wrong = hex.substring(1, 4);
System.out.println(wrong); // 2a0
```

The result `2a0` is not a complete byte slice aligned on two-character boundaries. You must use character indices 2 through 8:

```java
String correct = hex.substring(2, 8);
System.out.println(correct); // a0ff34
```

Or use `HexFormat.parseHex(hex, 2, 8)` to slice and parse into a byte array in one step.

### 8.2. Do Not Confuse Bit Indices with Byte Indices

A byte has 8 bits and two hex digits. If a protocol specifies an offset in bits, determine clearly whether the slice starts on a byte boundary. `HexFormat` operates on bytes and does not directly slice arbitrary bit groups.

If an offset or length is not divisible by 8 bits, apply appropriate bitmasks and shifts on bytes, and define the protocol's *bit order*. You cannot arbitrarily multiply or divide indices by byte counts.

## 9. Handling Delimited Hex Strings

If the format requires strings with `:`, create a matching parser:

```java
import java.util.HexFormat;

HexFormat colonFormat = HexFormat.ofDelimiter(":");

byte[] data = colonFormat.parseHex("12:a0:ff");
System.out.println(colonFormat.formatHex(data)); // 12:a0:ff
```

With this format, do not use `hex.length() / 2`, because the delimiter changes the character count. Let `HexFormat` parse according to its configuration and check the byte length after parsing:

```java
byte[] data = HexFormat.ofDelimiter(":").parseHex("12:a0:ff");

if (data.length != 3) {
    throw new IllegalArgumentException("Expected 3 bytes");
}
```

If you need to cap input before parsing, set a maximum character limit matching the expected byte count and delimiter. For a delimiter of length `d` characters, a string of `n` bytes generally has `2*n + d*(n-1)` characters when no prefix or suffix is present.

Delimiter formatting must be consistent. Do not strip arbitrary punctuation and whitespace while parsing, as doing so can accidentally accept malformed input or alter the meaning of the data.

## 10. Common Boundary Errors

### 10.1. Off-by-One

Bug:

```java
for (int i = offset; i <= offset + length; i++) {
    process(data[i]);
}
```

The loop above processes `length + 1` elements. If a slice of length 3 starts at 1, the valid indices are 1, 2, and 3.

Correct:

```java
for (int i = offset; i < offset + length; i++) {
    process(data[i]);
}
```

Or compute `endExclusive` after validating the range.

### 10.2. Allowing Negative Length

If you only check `offset + length <= data.length`, a negative `length` can slip past in some cases. Always ensure `length >= 0`.

### 10.3. Adding offset and length Before Validation

```java
int end = offset + length; // May overflow before checking.
if (end <= data.length) {
    // Not safe enough.
}
```

Validate with `Objects.checkFromIndexSize(offset, length, data.length)` first; only then compute `end`.

### 10.4. Slicing a Hex String at an Odd Position

Contiguous hex strings must be sliced along character pairs. Starting or ending in the middle of a pair yields a slice that does not represent complete bytes.

### 10.5. Trusting Sender-Declared Lengths

A header can declare a huge or negative size. Validate bounds before allocating arrays; do not let a client-controlled number directly dictate memory allocation.

### 10.6. Treating byte as an Unsigned Integer

Java `byte` ranges from -128 to 127. When displaying a byte value as an unsigned number, use:

```java
int unsignedValue = data[index] & 0xff;
System.out.printf("%02x%n", unsignedValue);
```

Bitwise AND with `0xff` keeps the low 8 bits and widens to an `int` in the range 0 to 255. `HexFormat` already formats a byte's bits properly, but when doing manual arithmetic or printing decimal values, keep the difference between signed bytes and unsigned octet values in mind.

## 11. Comprehensive Example: Reading a Bounded Hex Field

Suppose an application receives a non-delimited hex string and accepts at most 64 bytes. After parsing, it extracts a sub-slice for processing:

```java
import java.util.HexFormat;
import java.util.Objects;

public class BoundedHexData {
    private static final int MAX_BYTES = 64;

    static byte[] decode(String hex) {
        Objects.requireNonNull(hex, "hex");

        if ((hex.length() & 1) != 0) {
            throw new IllegalArgumentException("Hex length must be even");
        }
        if (hex.length() > 2L * MAX_BYTES) {
            throw new IllegalArgumentException("Payload exceeds 64 bytes");
        }

        return HexFormat.of().parseHex(hex);
    }

    static String segmentAsHex(byte[] data, int offset, int length) {
        Objects.requireNonNull(data, "data");
        Objects.checkFromIndexSize(offset, length, data.length);
        return HexFormat.of().formatHex(data, offset, offset + length);
    }

    public static void main(String[] args) {
        byte[] payload = decode("12a0ff345678");

        System.out.println("Byte count: " + payload.length);
        System.out.println("Segment: " + segmentAsHex(payload, 1, 3));
    }
}
```

Output:

```text
Byte count: 6
Segment: a0ff34
```

`decode` caps the size before creating the byte array. `segmentAsHex` validates the byte slice `[offset, offset + length)` and formats the requested segment directly.

In real applications, replace `MAX_BYTES` with a protocol limit or controlled configuration. Avoid taking an untrusted limit directly from the client.

## 12. Practice Exercises

### Exercise 1: Validating a Hex String Has Exactly 16 Bytes

Write a function that accepts a hex string and rejects it if:

- The string is null.
- The character count is odd.
- The length is not exactly 32 characters.
- Any character is outside `0-9`, `a-f`, `A-F`.

Hint: check length first, then use `HexFormat.of().parseHex(...)` to validate the contents.

### Exercise 2: Extracting 4 Bytes Starting at the 3rd Position

Given the byte array:

```java
byte[] data = {
        0x00, 0x11, 0x22, 0x33,
        0x44, 0x55, 0x66, 0x77
};
```

Extract the slice with `offset = 2`, `length = 4`. The expected hex output is `22334455`. Use `Objects.checkFromIndexSize` and `HexFormat.formatHex`.

### Exercise 3: Slicing a Byte Segment from a Hex String

Given the string `0011223344556677`, write a function to extract byte offset 2, length 4 without creating an intermediate substring. Hint: convert byte offset to char offset, validate the range, and call `HexFormat.parseHex(hex, from, to)`.

### Exercise 4: Validating Declared Length

A header declares a payload length. Write a function that rejects negative lengths or lengths exceeding 4096 bytes before allocation. After reading the payload, verify that the received byte count equals the declared length.

## 13. Key Takeaways for Hexadecimal Processing

- Contiguous hex strings have **2 characters per byte**; string length is not byte count.
- Slice ranges should use `[from, to)` with `to` exclusive.
- When callers pass `offset` and `length`, validate the range before computing `offset + length`.
- `Objects.checkFromIndexSize` is the right Java 17 API for safe range checks.
- `HexFormat` can format and parse a slice directly without always creating a subarray.
- For hex strings, distinguish character indices from byte indices; multiply byte indices by 2 when converting to character indices in non-delimited format.
- Validate input size before parsing or allocating memory.
- When using delimiters, prefixes, or suffixes, do not apply the contiguous hex string length formula.
- `byte` is signed in Java; use `& 0xff` when an unsigned octet value is needed.

## Official References

- [Java SE 17 API — `java.util.HexFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): formatting, parsing hex, and range-index overloads.
- [Java SE 17 API — `java.util.Objects`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `checkFromIndexSize` and index validation utilities.
- [Java SE 17 API — `java.util.Arrays`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): manipulating and copying array slices.
- [Java SE 17 API — `java.io.InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): reading bytes and handling actual bytes read.
- [Java SE 17 API — `java.io.DataInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readFully` when reading the full requested amount is required.
