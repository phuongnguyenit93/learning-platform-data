# Decoding `byte[]` to `String` with `Charset` and Decoding a Byte Range

## Objectives

Data read from files, sockets, HTTP, or a binary protocol often starts as a `byte[]`. To turn those bytes into Java text, you must **decode** them using the exact character encoding used when the data was created. Two important constructors are:

```java
new String(byte[] bytes, Charset charset)
new String(byte[] bytes, int offset, int length, Charset charset)
```

After this lesson, you will be able to choose the right `Charset`, understand `offset` and `length` measured in **bytes**, decode a sub-array without accidentally cutting across a Unicode character boundary, and recognize when input data is malformed.

## 1. Bytes Do Not Inherently Mean Characters

Java `String` stores Unicode text; `byte[]` stores a sequence of bytes. The same byte values can produce different text depending on the encoding.

For example, the character `é` is two bytes `C3 A9` in UTF-8, whereas in ISO-8859-1 it is one byte `E9`. Reading `E9` as a valid UTF-8 character will not produce `é`. Therefore, **the decoding charset must match the encoding charset**; specifying UTF-8 cannot magically fix data originally created with a different encoding.

`Charset` is in the `java.nio.charset` package. For common charsets, use the predefined constants in `StandardCharsets`:

```java
import java.nio.charset.StandardCharsets;

byte[] bytes = "Chào Java".getBytes(StandardCharsets.UTF_8);
String text = new String(bytes, StandardCharsets.UTF_8);
System.out.println(text);
```

Output:

```text
Chào Java
```

`getBytes(StandardCharsets.UTF_8)` is the **encoding** direction from `String` to `byte[]`; `new String(bytes, StandardCharsets.UTF_8)` is the reverse **decoding** direction. They form a round-trip when the data is representable in the chosen encoding and is not altered in transit.

Always specify the charset explicitly, especially for data exchanged between programs. The `new String(bytes)` constructor uses the default charset of the running Java environment; do not rely on the default when a protocol or file format specifies a particular charset.

## 2. Decoding an Entire Array: `new String(byte[], Charset)`

Syntax:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
```

Where:

- `bytes`: the byte array containing encoded text data.
- `StandardCharsets.UTF_8`: the `Charset` used to interpret the byte sequence.
- `text`: a new `String` object containing the decoded text.

The constructor decodes the **entire** array from index `0` to `bytes.length - 1`. If the array is empty, the result is the empty string `""`. Passing `null` for `bytes` or `charset` is invalid and throws `NullPointerException`.

Example with predefined UTF-8 data:

```java
byte[] encoded = {(byte) 0x43, (byte) 0x61, (byte) 0x66,
                  (byte) 0xC3, (byte) 0xA9};

String decoded = new String(encoded, StandardCharsets.UTF_8);
System.out.println(decoded);
```

Output:

```text
Café
```

ASCII bytes `43 61 66` give `Caf`; the UTF-8 pair `C3 A9` gives `é`. The `(byte)` cast here is needed for hex literals greater than `0x7F` because Java's `byte` type is signed (range -128 to 127). Negative signs when displaying a byte array do not mean the encoded data changed.

After the constructor finishes, modifying elements of the input array **does not alter the contents of the created `String`**. This is consistent with the immutability of `String`.

## 3. Decoding a Range: `new String(byte[], offset, length, Charset)`

Many messages contain a header, text payload, and binary trailer. If only the middle portion is text, decode the exact specified range:

```java
String text = new String(bytes, offset, length, StandardCharsets.UTF_8);
```

**Parameter meanings:**

| Parameter | Meaning |
| --- | --- |
| `bytes` | The entire source byte array |
| `offset` | Index of the **first byte** of the range to read, starting from 0 |
| `length` | **Number of bytes** to decode, not the ending byte index |
| `charset` | Character encoding of the text byte section |

The selected range spans indices **`[offset, offset + length)`**: inclusive of the byte at `offset` and exclusive of the byte at `offset + length`. This matches the standard half-open interval convention used throughout Java.

```text
Byte array: [H0] [H1] [C] [a] [f] [C3] [A9] [T]
Index:      0    1    2   3   4    5    6    7
                       <------ 5 bytes ----->
                       offset=2, length=5
```

In this illustration, `H0`/`H1` is the header and `T` is the trailer. The byte sequence from position 2 to 6 corresponds to the UTF-8 text `Café`. Both `C3` and `A9` must lie inside the decoded range to form the character `é`.

Example:

```java
byte[] packet = {
        0x01, 0x02,             // Header
        0x43, 0x61, 0x66,
        (byte) 0xC3, (byte) 0xA9, // "Café" in UTF-8
        0x7F                    // Trailer
};

String payload = new String(packet, 2, 5, StandardCharsets.UTF_8);
System.out.println(payload);
```

Output:

```text
Café
```

If you only need to decode, using the range constructor is more convenient than creating a temporary array with `Arrays.copyOfRange(bytes, offset, offset + length)` and then calling `new String(...)`. However, the constructor still has to process the bytes and allocate the output string; "not slicing the array manually" **does not mean zero-allocation decoding**.

### Bounds Checking

`offset` and `length` must be non-negative, and the range must lie completely within `bytes`. If it goes out of bounds, the constructor throws `IndexOutOfBoundsException`. For example:

```java
byte[] data = {65, 66, 67}; // "ABC"
String value = new String(data, 1, 2, StandardCharsets.UTF_8);
// Result: "BC"
```

`new String(data, 1, 3, StandardCharsets.UTF_8)` exceeds the array length and fails. `offset=1, length=2` selects the bytes at indices 1 and 2, **not** "from index 1 to index 2" as if `length` were an end index.

`length=0` produces an empty string if `offset` is valid (including `offset == bytes.length`).

## 4. Choosing Byte Boundaries Compatible with the Charset

With UTF-8, a single Unicode character can take from one to four bytes. `offset` and `length` are **byte** coordinates, so a byte range that is valid with respect to array bounds can still cut right through the encoded sequence of a character.

Example:

```java
byte[] eAcute = {(byte) 0xC3, (byte) 0xA9};

System.out.println(new String(eAcute, 0, 2, StandardCharsets.UTF_8));
System.out.println((int) new String(eAcute, 0, 1, StandardCharsets.UTF_8).charAt(0));
```

Output:

```text
é
65533
```

Decoding both bytes yields `é`; taking only the first byte `C3` leaves UTF-8 missing its continuation byte, so the constructor substitutes the Unicode replacement character **U+FFFD**, which has decimal value 65533. This is not an array index error, but a **byte sequence error after slicing the range**.

If you want to extract a range by character count in the **decoded text**, decode the valid data first, then use the appropriate `String` APIs. In particular, `String.length()` counts UTF-16 code units, not bytes and not always Unicode code points.

If data arrives in multiple chunks from a network and a UTF-8 character straddles two chunks, do not decode each chunk independently and expect always-accurate results. Buffer enough bytes before decoding, or use `CharsetDecoder` for incremental decoding that preserves state across chunks.

## 5. Invalid Bytes and Error-Control Modes

The two `String` constructors taking `Charset` above **replace malformed or unmappable byte sequences with the charset's default replacement string**. With UTF-8, you commonly see the replacement character `�` (`U+FFFD`) in the output.

```java
byte[] badUtf8 = {(byte) 0xC3, (byte) 0x28};
String text = new String(badUtf8, StandardCharsets.UTF_8);

System.out.println((int) text.charAt(0));
System.out.println(text.charAt(1));
```

Output:

```text
65533
(
```

Byte `C3` requires a valid UTF-8 continuation byte, which `28` is not; the invalid byte is replaced with `U+FFFD`, while `28` is interpreted as `(`. Replacement behavior allows displaying damaged data without crashing, but it can **hide input corruption**.

When strict validation is required—for example, reading identifiers, protocol messages, or data that must be verified—use `CharsetDecoder` and configure it to report errors:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

byte[] badUtf8 = {(byte) 0xC3, (byte) 0x28};

CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    String text = decoder.decode(ByteBuffer.wrap(badUtf8)).toString();
    System.out.println(text);
} catch (CharacterCodingException error) {
    System.out.println("Invalid UTF-8 data");
}
```

Output:

```text
Invalid UTF-8 data
```

This is an **illustrative snippet** to place inside a method or `main`; the `import` statements go at the top of the file. `REPORT` asks the decoder to throw an error instead of silently substituting characters. When you only want to decode a sub-range with a decoder, use `ByteBuffer.wrap(bytes, offset, length)` to create a buffer whose position and limit match the byte range. `CharsetDecoder` is stateful and should not be shared across threads without proper synchronization.

## 6. Complete Runnable Java 17+ Program

Create a file named **`ByteDecodingDemo.java`** with the following content:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class ByteDecodingDemo {
    public static void main(String[] args) {
        byte[] prefix = {0x01, 0x02, 0x03};
        byte[] content = "Chào Java".getBytes(StandardCharsets.UTF_8);
        byte[] suffix = {0x7F};
        byte[] packet = new byte[prefix.length + content.length + suffix.length];

        System.arraycopy(prefix, 0, packet, 0, prefix.length);
        System.arraycopy(content, 0, packet, prefix.length, content.length);
        System.arraycopy(suffix, 0, packet,
                prefix.length + content.length, suffix.length);

        String allTextBytes = new String(content, StandardCharsets.UTF_8);
        String selectedText = new String(
                packet, prefix.length, content.length, StandardCharsets.UTF_8);

        System.out.println("Full decode: " + allTextBytes);
        System.out.println("Range decode: " + selectedText);
        System.out.println("UTF-16 units: " + selectedText.length());
        System.out.println("UTF-8 bytes: " + content.length);

        byte[] invalid = {(byte) 0xC3, (byte) 0x28};
        String replaced = new String(invalid, StandardCharsets.UTF_8);
        System.out.println("Replacement char code: " + (int) replaced.charAt(0));

        CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            strict.decode(ByteBuffer.wrap(invalid));
            System.out.println("Valid data");
        } catch (CharacterCodingException ex) {
            System.out.println("Invalid data");
        }
    }
}
```

Compile the file saved as UTF-8 and run it:

```bash
javac -encoding UTF-8 ByteDecodingDemo.java
java ByteDecodingDemo
```

Output displayed on a Unicode-capable console:

```text
Full decode: Chào Java
Range decode: Chào Java
UTF-16 units: 9
UTF-8 bytes: 10
Replacement char code: 65533
Invalid data
```

Explanation: `"Chào Java"` consists of 9 UTF-16 code units but 10 UTF-8 bytes, because the letter `à` is encoded in two bytes. `packet` contains three header bytes, ten text bytes, and one trailer byte. The four-parameter constructor reads only the exact ten text bytes; the two binary sections do not enter the result. The final block contrasts the constructor's character-replacement behavior with the decoder's error-reporting mechanism.

## 7. Practical Notes and Common Mistakes

| Situation | Cause or How to Handle |
| --- | --- |
| Vietnamese text turns into `�` or strange characters | Check the source charset and byte validity; do not assume UTF-8 if the actual format differs |
| Accidentally including header or trailer bytes | Compute `offset` from the start of the array and `length` as the exact byte count of the payload |
| Splitting in the middle of a multi-byte character | Pick proper encoded boundaries, or decode in streaming fashion with a stateful decoder |
| `IndexOutOfBoundsException` | Double-check byte indices, length, and array bounds |
| Corrupted data but the program throws no exception | The `String` constructor is using replacement mode; switch to `CharsetDecoder` with `REPORT` if needed |
| Using `String.length()` to compute message byte size | `String` length is the number of UTF-16 units; use `byte[]` length when the protocol requires byte count |
| UTF-8 file starting with a BOM | Bytes `EF BB BF` represent `U+FEFF`; when decoding UTF-8 into `String`, check for and strip this mark if the file format requires removing BOM |
| Passing user data to `new String(bytes)` without specifying a charset | Specify the protocol's charset, e.g., `StandardCharsets.UTF_8`, so data is interpreted consistently |

Do not confuse `new String(bytes, 2, 5, UTF_8)` with `substring(2, 5)`: `substring` takes positions in the decoded Java text and its second argument is an **exclusive end index**; the byte-range constructor takes a **byte count**. The two operations use different units and have different meanings.

## 8. Self-Check

**Question 1.** Given `byte[] data = {65, 66, 67, 68};`, what is the value of `new String(data, 1, 2, StandardCharsets.US_ASCII)`?

**Answer:** `"BC"`. The decoded range consists of bytes at indices 1 and 2, corresponding to ASCII codes 66 and 67.

**Question 2.** Why can `new String(utf8, 0, 1, UTF_8)` produce `�` even though index `0` and length `1` are both in bounds?

**Answer:** The first byte may be the leading byte of a two-to-four-byte UTF-8 character. The byte range does not contain the full encoded sequence, so the input is invalid to the decoder.

**Question 3.** When should you use `CharsetDecoder` instead of a `String` constructor?

**Answer:** When you need to detect invalid data instead of silently substituting replacement characters, or when decoding chunked data while preserving state across reads.

## Key Takeaways

Use **`new String(bytes, charset)`** to decode an entire byte array and **`new String(bytes, offset, length, charset)`** to decode the exact byte range of a payload. `offset` is the starting byte index, `length` is the **number of bytes**, and the charset must match the source data. With UTF-8, pay close attention to multi-byte character boundaries and use `CharsetDecoder` when input errors must be validated.
