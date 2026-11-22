# Converting byte[] to String with an Explicit Charset in Java

When reading data from a `ByteArrayOutputStream`, a small file, a socket, a buffer, or an API returning `byte[]`, a program often needs to recover **text** as a `String`. This seemingly simple conversion is only accurate when you know **which charset those bytes were encoded with** and explicitly decide how to handle invalid byte sequences.

In Java 17+, the standard idiom is:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
```

Here, `bytes` is a `byte[]` array already containing **UTF-8 encoded text data**, and `StandardCharsets.UTF_8` is the charset defined by the data contract. This snippet requires `import java.nio.charset.StandardCharsets;`.

This article belongs to the **In-Memory I/O** group: converting byte arrays to strings, specifying the right charset, understanding misdecoding errors, choosing how invalid bytes are handled, and knowing when to stream instead of loading all data into memory.

## 1. Do Not Confuse Bytes with Characters

A Java `byte[]` is a collection of 8-bit units. It **carries no charset metadata**; for instance, the bytes `C3 A9` do not by themselves state that they represent the letter `é`.

```text
String --encode (using UTF-8)--> byte[]
   "é"                           C3 A9
                                   |
                         decode (using UTF-8)
                                   |
                                   v
                                  "é"
```

If those same bytes `C3 A9` are decoded using ISO-8859-1, you get two characters corresponding to `Ã` and `©`, typically displayed as `"Ã©"`. Thus, the exact same `byte[]` can produce different `String` values depending on the charset.

Distinguish three concepts:

- **Byte:** the raw data unit; a `byte[]` may contain text, a PNG image, a ZIP file, binary encoding, or compressed data.
- **Java character:** `String` uses UTF-16 code units; `char` is a 16-bit unit, while a code point outside the BMP may require two `char`s.
- **Charset:** the rules that map a sequence of characters to bytes and bytes back to characters, such as UTF-8, UTF-16, US-ASCII, or ISO-8859-1.

There is no valid `(String) bytes` cast for `byte[]`. Nor should you use `Arrays.toString(bytes)` to decode text: that method produces a **textual representation of the numeric byte values**, such as `[65, 66]`, rather than `"AB"`.

## 2. The Preferred Constructor: new String(byte[], Charset)

Syntax:

```java
byte[] bytes = { 72, 101, 108, 108, 111 };
String text = new String(bytes, StandardCharsets.UTF_8);
System.out.println(text); // Hello
```

This illustrative snippet requires importing `StandardCharsets`. Because the data consists solely of ASCII bytes, UTF-8 decoding maps each byte to one character as expected.

Primary APIs:

```java
new String(byte[] bytes, Charset charset)
new String(byte[] bytes, int offset, int length, Charset charset)
```

- `bytes`: the input byte array to decode.
- `charset`: the explicitly specified character encoding; typically a constant from `StandardCharsets`.
- `offset`: the **starting byte index** in the array.
- `length`: the **number of bytes to decode**, not the ending byte index, and not the number of characters that will be produced.
- The result is a new `String` containing the decoded character units. Modifying `bytes` afterward does not change the contents of the created `String`.
- Passing `null` for required arguments or an invalid offset/length fails the operation; validate inputs before decoding if they come from external sources.

This style expresses the **data format contract** directly at the conversion point, without relying on the host machine's default charset, locale settings, or console rendering.

### Common Charsets

| Charset | Characteristics | When to Use |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | Unicode; each code point takes 1 to 4 bytes | Sensible default for modern text formats when the protocol/file specifies UTF-8 |
| `StandardCharsets.US_ASCII` | 7-bit ASCII | Protocols strictly limited to ASCII |
| `StandardCharsets.ISO_8859_1` | Each byte 0–255 maps to the corresponding Unicode character | Legacy data with a Latin-1 contract |
| `StandardCharsets.UTF_16BE` | Big-endian UTF-16 without emitting a BOM | Data explicitly specified as UTF-16BE |
| `StandardCharsets.UTF_16LE` | Little-endian UTF-16 without emitting a BOM | Data explicitly specified as UTF-16LE |
| `StandardCharsets.UTF_16` | UTF-16 with BOM and byte-order rules per the charset specification | Data explicitly declared as UTF-16 |

**Do not choose ISO-8859-1 merely because it can decode every byte:** the result may be meaningless text. Likewise, do not guess UTF-8 when the source format explicitly specifies another charset. For charsets not in `StandardCharsets`, use `Charset.forName("...")` once the name is verified and supported by the runtime provider; an invalid or unsupported name will fail at lookup time.

## 3. Why Must You Specify the Charset Explicitly?

The following two constructors are not equivalent in output determinism:

```java
String implicit = new String(bytes);
String explicit = new String(bytes, StandardCharsets.UTF_8);
```

`new String(bytes)` uses the Java environment's **default charset**. In Java 17, the default can depend on the operating system and configuration. Starting with Java 18, UTF-8 is the default under JEP 400 in standard configurations, yet code exchanging data with other systems **should still declare the charset explicitly**.

Risks of relying on an implicit charset:

1. A file written in UTF-8 may read correctly on machine A yet break accents on machine B with a different default charset.
2. A program may work in an IDE yet yield different output when run in a batch job, container, or differently configured runtime.
3. The receiving side cannot clearly tell why bytes turned into particular characters, making debugging harder.

Durable rule: **the producer of bytes and the consumer of bytes must agree on the charset via a data specification**. For instance, if a config file specifies UTF-8, both sides use UTF-8; HTTP must honor the protocol and `Content-Type` rules; a legacy file defined as Windows-1252 must use that charset if the runtime supports it.

## 4. Complete Java 17+ Example: String → byte[] → String

Create file `ByteArrayToStringDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.OutputStreamWriter;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import java.util.Locale;
import java.util.stream.Collectors;

public class ByteArrayToStringDemo {
    public static void main(String[] args) throws Exception {
        String original = "Ch\u00E0o Java \u2615";
        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);

        System.out.println("UTF-8 bytes: " + utf8.length);
        System.out.println("Hex: "
                + HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(utf8));

        String restored = new String(utf8, StandardCharsets.UTF_8);
        System.out.println("Round trip: " + original.equals(restored));

        // Decode only 3 bytes starting at index 1: 41 C3 A9 = "Aé".
        byte[] frame = {
                0x21, 0x41, (byte) 0xC3, (byte) 0xA9, 0x3F
        };
        String slice = new String(frame, 1, 3, StandardCharsets.UTF_8);
        System.out.println("Slice A\u00E9: " + "A\u00E9".equals(slice));

        // Same 2 bytes, but a charset that does not match the source.
        byte[] eAcute = { (byte) 0xC3, (byte) 0xA9 };
        String wronglyDecoded =
                new String(eAcute, StandardCharsets.ISO_8859_1);
        System.out.println("Wrong charset equal: "
                + "\u00E9".equals(wronglyDecoded));

        // C3 28 is invalid UTF-8; the String constructor applies replacement policy.
        byte[] bad = { (byte) 0xC3, (byte) 0x28 };
        String forgiving = new String(bad, StandardCharsets.UTF_8);
        String points = forgiving.codePoints()
                .mapToObj(cp -> "U+" + Integer.toHexString(cp)
                        .toUpperCase(Locale.ROOT))
                .collect(Collectors.joining(" "));
        System.out.println("Decoded error code points: " + points);

        // Same invalid data, but a strict decoder rejects it.
        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bad));
        } catch (CharacterCodingException e) {
            System.out.println("Strict decoder: "
                    + e.getClass().getSimpleName());
        }

        // Retrieve byte[] from an in-memory OutputStream, then decode.
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (OutputStreamWriter writer =
                     new OutputStreamWriter(sink, StandardCharsets.UTF_8)) {
            writer.write("Hi \u2615");
        }
        System.out.println("BAOS toString Charset: "
                + "Hi \u2615".equals(sink.toString(StandardCharsets.UTF_8)));
    }
}
```

Compile and run:

```bash
javac ByteArrayToStringDemo.java
java ByteArrayToStringDemo
```

Stdout verified with JDK:

```text
UTF-8 bytes: 14
Hex: 43 68 C3 A0 6F 20 4A 61 76 61 20 E2 98 95
Round trip: true
Slice Aé: true
Wrong charset equal: false
Decoded error code points: U+FFFD U+28
Strict decoder: MalformedInputException
BAOS toString Charset: true
```

Explanation:

- `"Chào Java ☕"` has 14 UTF-8 bytes: `à` is `C3 A0`, while `☕` is `E2 98 95`. `utf8.length` counts bytes and therefore differs from the character count.
- Decoding with the same UTF-8 charset produces a string equal to the original; `original.equals(restored)` returns `true`.
- `frame` has two marker bytes at the ends (`!` and `?`). `new String(frame, 1, 3, UTF_8)` uses only the three bytes `41 C3 A9`, producing `"Aé"` without pulling in bytes outside the selected range.
- Decoding `C3 A9` with ISO-8859-1 does not yield the single character `é`, so the equality check returns `false`.
- The byte `C3` followed by `28` does not form a valid UTF-8 sequence. The `String` constructor with a charset replaces the malformed sequence with `U+FFFD` while retaining the `(` character as `U+28`.
- A `CharsetDecoder` configured with `REPORT` rejects that input and throws `MalformedInputException`.
- `ByteArrayOutputStream` connects this lesson directly to **in-memory I/O**: `OutputStreamWriter` encodes characters into bytes, and `toString(StandardCharsets.UTF_8)` decodes the written bytes.

The example intentionally prints most results as numbers, hex, or booleans so it does not depend on the terminal's ability to render Vietnamese diacritics or emojis.

## 5. Decoding a Slice of byte[]: offset and length Are in Bytes

Constructor:

```java
String text = new String(bytes, offset, length, charset);
```

This means: start at index `offset` in the array, take **exactly `length` bytes**, and decode that slice. `length` is not `endIndex`, and exceeding the array bounds is not permitted.

Example `byte[]` contents:

```text
index: 0   1   2   3   4
byte:  21  41  C3  A9  3F
       !   A    \--é--/ ?
```

`new String(bytes, 1, 3, UTF_8)` takes `41 C3 A9` and produces `"Aé"`. Two calls that are often confused:

```java
new String(bytes, 1, 3, StandardCharsets.UTF_8); // bytes 1, 2, 3
new String(bytes, 1, 4, StandardCharsets.UTF_8); // bytes 1, 2, 3, 4
```

The second line takes four bytes, including byte `3F` (`?`). **`offset + length` may reach at most `bytes.length`** and must not exceed it. If offset/length values arrive from a network packet or untrusted data structure, validate carefully to prevent negative indices, out-of-bounds access, or integer overflow. A safe check when all variables are `int`:

```java
if (offset < 0 || length < 0
        || offset > bytes.length
        || length > bytes.length - offset) {
    throw new IllegalArgumentException("Invalid byte slice");
}
String part = new String(bytes, offset, length, StandardCharsets.UTF_8);
```

This is an **illustrative code snippet** assuming `bytes`, `offset`, and `length` are already defined.

### Do Not Split in the Middle of a UTF-8 Character

For example, the UTF-8 bytes of `é` are `C3 A9`. If you slice just the first byte `C3` and call:

```java
new String(new byte[] { (byte) 0xC3 }, StandardCharsets.UTF_8);
```

The constructor does not receive enough data to reconstruct `é`; under its error-replacement rule, it outputs the replacement character `U+FFFD`. Slicing an array at valid array indices **does not guarantee valid character boundaries**.

Distinguish these cases:

- If a format specifies **byte offsets and lengths**, ensure they land on valid character boundaries for that charset; or use an incremental decoder that preserves incomplete bytes for the next chunk.
- If you want to slice **by Java characters**, decode the valid data first and then operate on the `String`. If you need to slice by Unicode code points, use the `codePoint*` APIs because `String.substring` still operates on UTF-16 positions and can split a surrogate pair.
- If data consists of multiple messages, extract byte slices using framing or message byte lengths rather than relying on `String.length()`.

## 6. In-Memory byte[]: Key APIs to Know

### 6.1. ByteArrayOutputStream → byte[] → String

`ByteArrayOutputStream` is an `OutputStream` that writes bytes into an in-memory buffer. Once writing finishes:

```java
ByteArrayOutputStream out = new ByteArrayOutputStream();
out.write(new byte[] { 65, 66, 67 });
byte[] bytes = out.toByteArray();
String text = new String(bytes, StandardCharsets.US_ASCII); // "ABC"
```

This is a code snippet requiring `java.io.ByteArrayOutputStream` and `java.nio.charset.StandardCharsets`. `toByteArray()` **creates a copy** of the bytes currently in the buffer; the result does not include unused capacity.

Java also offers a shorter form:

```java
String text = out.toString(StandardCharsets.UTF_8);
```

`ByteArrayOutputStream.toString(Charset)` decodes **all bytes currently in the buffer** using the chosen charset, which is convenient when the final goal is a `String`. This overload was added in Java 10 and works in Java 17+. The no-argument `out.toString()` depends on the default charset, so avoid using it for data exchanged across different environments.

A `ByteArrayOutputStream` can still be read after `close()` because closing this stream type does not invalidate its in-memory contents. **Do not assume that every OutputStream remains readable or writable after close.**

### 6.2. ByteArrayInputStream Holds Bytes, Not a String Directly

`ByteArrayInputStream` reads a byte array as a stream source:

```java
byte[] bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
try (ByteArrayInputStream in = new ByteArrayInputStream(bytes)) {
    byte[] allBytes = in.readAllBytes();
    String text = new String(allBytes, StandardCharsets.UTF_8);
}
```

This snippet requires importing `java.io.ByteArrayInputStream` and `java.nio.charset.StandardCharsets`. `InputStream.readAllBytes()` was introduced in Java 9. This helps demonstrate byte streaming, though if you **already have the original byte array**, you can call `new String(bytes, UTF_8)` directly; wrapping it in an `InputStream` just to read it back for conversion is unnecessary.

When processing large streams or chunked data, an `InputStreamReader(in, UTF_8)` may be more appropriate because it decodes bytes into characters incrementally instead of buffering all bytes into one large array.

### 6.3. ByteBuffer Differs from byte[]

When using Java NIO, read bytes may sit in a `ByteBuffer` with `position` and `limit`. Never assume `buffer.array()` always exists (direct or read-only buffers may have no accessible backing array), or that `array()` matches only the valid bytes. Only the bytes between `position` and `limit` are the **remaining bytes** to decode.

Example:

```java
ByteBuffer buffer = ByteBuffer.wrap(
        "OK".getBytes(StandardCharsets.UTF_8));
String text = StandardCharsets.UTF_8.decode(buffer).toString();
```

This snippet requires importing `java.nio.ByteBuffer` and `java.nio.charset.StandardCharsets`. `Charset.decode(ByteBuffer)` is a convenience method with a replacement policy for invalid data; if invalid bytes must be rejected, use a `CharsetDecoder` configured with `CodingErrorAction.REPORT`.

## 7. Wrong Charset Produces Garbled Characters: Mojibake

Suppose we have UTF-8 bytes:

```text
é → C3 A9 (UTF-8)
```

Decoding them with ISO-8859-1 yields:

```java
byte[] utf8 = { (byte) 0xC3, (byte) 0xA9 };
String right = new String(utf8, StandardCharsets.UTF_8);        // "é"
String wrong = new String(utf8, StandardCharsets.ISO_8859_1);  // "Ã©"
```

This is a standalone example of byte mapping; ISO-8859-1 **still decodes them into valid characters**, just with the wrong meaning relative to the UTF-8-encoded source. Hence **no exception is thrown** merely because accents render incorrectly.

When suspecting a charset mismatch:

1. Identify **what produced the bytes** and what charset the format documentation, headers, or metadata specify.
2. Inspect the actual bytes in hex if needed; for example, `C3 A9` corresponds to UTF-8 `é`.
3. Fix the **charset at the byte-decoding step** to match the real contract; avoid patching broken output with chains of `replace(...)` calls on already-garbled characters.
4. If data was misdecoded and you still have the **original bytes**, decode again from the original bytes. Once the original bytes are gone and content has passed through lossy transformations, full recovery is not always possible.
5. Do not "guess the charset" from a short `byte[]` and treat the result as certain. Many charsets produce plausible-looking text, especially for ASCII-heavy payloads.

Every byte from `0x00` to `0x7F` in basic ASCII is encoded identically in UTF-8 and US-ASCII; therefore, tests using only `"ABC"` do not prove Vietnamese decoding works. Include accented characters, emojis, or non-ASCII characters when testing Unicode text protocols.

## 8. Invalid UTF-8 Data: The String Constructor May Silently Replace Bytes

The byte sequence:

```text
C3 28
```

is invalid UTF-8, because `C3` starts a two-byte sequence yet `28` is not a continuation byte. When calling:

```java
byte[] bad = { (byte) 0xC3, (byte) 0x28 };
String text = new String(bad, StandardCharsets.UTF_8);
```

The `String(byte[], Charset)` constructor **replaces** malformed/unmappable byte sequences with the replacement character used during decoding and does not throw `CharacterCodingException`. In Java's UTF-8 decoder, the sequence above becomes `U+FFFD` followed by `U+0028` (`(`).

This is useful for UI previews of damaged data, but becomes problematic when:

- The format requires **strictly valid UTF-8**.
- A system signs or verifies data and must preserve exact information.
- Filenames, identifiers, protocol fields, or critical data must not have characters silently altered or dropped.
- Software needs to report precisely which message or file contains truncated bytes.

### Using CharsetDecoder to Reject Invalid Bytes

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8Example {
    public static void main(String[] args) {
        byte[] bytes = { (byte) 0xC3, (byte) 0x28 };

        try {
            String text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
            System.out.println("Valid UTF-8: " + text);
        } catch (CharacterCodingException e) {
            System.out.println("Rejected: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Save as `StrictUtf8Example.java` and run:

```bash
javac StrictUtf8Example.java
java StrictUtf8Example
```

Stdout:

```text
Rejected: MalformedInputException
```

A newly created `CharsetDecoder` defaults to `REPORT`, yet setting both error actions explicitly clarifies intent and highlights how it differs from the `String` constructor. Both `MalformedInputException` and `UnmappableCharacterException` extend `CharacterCodingException`. When input is invalid, fail appropriately; never take a string with substituted characters and treat it as successfully validated.

Do not confuse `new String(bytes, charset)` with `charset.newDecoder().decode(ByteBuffer.wrap(bytes))`: they differ in their **input error-handling policy**. The convenience method `Charset.decode(ByteBuffer)` also uses replacement mode, so it does not substitute for a strict decoder.

## 9. Some Bytes Are Not Text Content

Byte arrays returned from files or APIs **may be binary data**, such as JPEG/PNG images, ZIP/GZIP archives, protobuf payloads, or encrypted messages. Never call `new String(binaryBytes, UTF_8)` directly and try to treat the result as a faithful copy of the original data:

- Not every byte sequence is valid UTF-8.
- When decoding errors trigger replacement mode, many distinct byte sequences collapse into the same `U+FFFD` character.
- Re-encoding `text.getBytes(UTF_8)` afterward **cannot guarantee recovering the original bytes**.
- Binary data contains `0` bytes, control bytes, and structures that do not correspond to text.

If the requirement is to **represent binary data safely using ASCII characters for text transport or storage**, use Base64 or hex rather than treating arbitrary bytes as text.

Example:

```java
byte[] binary = { 0x00, (byte) 0xFF, 0x10 };
String encoded = Base64.getEncoder().encodeToString(binary);
byte[] recovered = Base64.getDecoder().decode(encoded);
boolean exact = Arrays.equals(binary, recovered); // true
```

This illustrative snippet requires importing `java.util.Base64` and `java.util.Arrays`. This is **binary-to-text encoding**, not the UTF-8 charset. Base64 neither turns binary data into meaningful Unicode prose nor provides cryptographic encryption.

## 10. UTF-8 BOM and Prefixed Data

Some UTF-8 sources place a **BOM** (`EF BB BF`) at the start of the content. Decoding those bytes with UTF-8 can produce a leading `U+FEFF` character at the start of the string. Consequently, if you expect the string to start with `"ABC"` when it actually starts with `"\uFEFFABC"`, `startsWith("ABC")` will fail.

You should not blindly strip the first three bytes from every byte array:

- Not every UTF-8 document has a BOM.
- Those first three bytes might be genuine payload bytes in another protocol.
- Other charsets such as UTF-16 have different BOM rules.
- How a BOM is handled can depend on the codec/API and file format; consult the source specification.

Only when the specification allows a BOM and the reader does not already strip it should you consider removing a **leading `U+FEFF` character** after decoding, provided the application does not need to preserve it as content. Replacing every `U+FEFF` across the entire string is excessive.

## 11. Reading an Entire File into Memory When Size Permits

When a text file is small, the code is straightforward:

```java
Path path = Path.of("message.txt");
byte[] rawBytes = Files.readAllBytes(path);
String text = new String(rawBytes, StandardCharsets.UTF_8);
```

This snippet requires importing `java.nio.file.Files`, `java.nio.file.Path`, and `java.nio.charset.StandardCharsets`, plus handling `IOException`. `Files.readAllBytes` loads the entire content, and `new String` decodes it. It is simple, though it holds **both the byte array and the String** in memory and applies replacement policy on invalid bytes.

If the file is very large, comes from a continuous stream, or needs line-by-line processing, prefer:

```java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process one line and continue.
    }
}
```

This illustrative snippet requires importing `java.io.BufferedReader` and the NIO classes above, while handling `IOException`. The reader API decodes on the fly, avoiding loading the whole file into a `byte[]`. If strict byte validation is needed, use `InputStreamReader` with a `CharsetDecoder` configured with `REPORT`.

### ByteArrayOutputStream and String for Small Payloads

When writing text to a `ByteArrayOutputStream`, there are two directions:

```text
String --OutputStreamWriter(UTF-8)--> ByteArrayOutputStream
                                          |
                                      toByteArray()
                                          |
                                          v
                                      byte[] UTF-8
                                          |
                                      new String(bytes, UTF_8)
                                          |
                                          v
                                        String
```

This structure is useful in unit tests—for example, when verifying textual output produced by an API writing to an `OutputStream`. When exact byte comparison is needed (protocols, signatures), compare `byte[]` before decoding; when comparing textual content, decode with the right charset and compare `String`.

## 12. Performance, Copying, and Immutability

- The `new String(bytes, charset)` constructor creates a `String` object from decoded data. Never assume it is a direct "view" over `byte[]`: mutating the byte array afterward does not change the `String`.
- Decoding incurs CPU and memory allocation cost; avoid repeatedly decoding the same `byte[]` inside a hot loop just to check a condition better tested at the byte level.
- `String.length()` returns the number of **UTF-16 code units**, not input bytes. `"é"` has one `char` unit yet two UTF-8 bytes; an emoji outside the BMP has two `char`s and four UTF-8 bytes.
- `bytes.length` is the byte length after encoding or reading from a source; if you need the exact byte length of a message in UTF-8, measure the **encoded bytes**, not `text.length()`.
- Do not use `new String(bytes, charset)` as a round-trip verification check if the source might contain invalid byte sequences and byte loss is unacceptable: validate with a strict decoder first.
- When processing bytes read in chunks, never decode each chunk independently via the `String` constructor if multi-byte characters could be split across boundaries. Use an incremental decoder or `InputStreamReader` to retain state across chunk boundaries.

Example of a chunk-splitting bug:

```text
UTF-8 bytes of "é": C3 A9
Chunk #1: C3
Chunk #2: A9

new String(chunk1, UTF_8) + new String(chunk2, UTF_8)
→ does not equal "é" (both chunks lack complete sequences).

Decode C3 A9 together or preserve decoder state across chunks
→ "é".
```

## 13. Common Mistakes and Fixes

| Mistake | Problem | Correct Approach |
| --- | --- | --- |
| `new String(bytes)` for exchanged data | Depends on the default charset | `new String(bytes, StandardCharsets.UTF_8)` or the contract's charset |
| Decoding UTF-8 bytes as ISO-8859-1 | Mojibake / broken accents without throwing an exception | Verify and use the original charset |
| Treating arbitrary `byte[]` as text | Binary data is corrupted when passed through `String` | Keep bytes intact; use Base64/hex for text representation |
| Using `Arrays.toString(bytes)` to get text | Produces numeric representation of bytes | `new String(bytes, charset)` |
| Using `String.length()` as payload byte size | Wrong byte count; may cut mid-character | Compute byte length after encoding |
| Passing `length` as an end-index | Decodes the wrong slice or exceeds bounds | `length` is the byte count starting from `offset` |
| Splitting across UTF-8 bytes and decoding separately | Produces `U+FFFD` or errors | Respect character boundaries or use an incremental decoder |
| Using `String` constructor to validate UTF-8 | Malformed bytes are silently replaced | `CharsetDecoder` with `REPORT` |
| Assuming wrong-charset decoding always throws | Many charsets produce valid strings with wrong text | Rely on metadata/protocol and inspect hex |
| Calling `toString()` on `byte[]` | Returns type name and identity hash, not contents | `new String(bytes, charset)` |
| Forgetting to close file streams/readers | Resource leak | `try-with-resources` |
| Reading huge files with `readAllBytes` then decoding | High memory pressure | `BufferedReader`/`InputStreamReader` streaming incrementally |
| Stripping BOM unconditionally regardless of source | Corrupts data or drops valid bytes | Apply BOM handling per the actual format specification |

## 14. Review Questions

1. **Does a `byte[]` array have its own charset?** No. It only holds raw bytes; the charset is determined by the format or external agreement.
2. **What is the reliable way to convert UTF-8 bytes to a String?** `new String(bytes, StandardCharsets.UTF_8)`.
3. **Why can `C3 A9` become either `"é"` or `"Ã©"`?** Because UTF-8 and ISO-8859-1 interpret the same bytes under different rules.
4. **Which indices does `new String(bytes, 2, 5, UTF_8)` read?** Five bytes at indices 2, 3, 4, 5, and 6; `5` is the length.
5. **What happens if the array only contains the first byte `C3` of `é`?** Decoding as UTF-8 via the `String` constructor replaces the malformed/truncated byte instead of producing `é`.
6. **How do you reject invalid UTF-8 bytes?** Use `UTF_8.newDecoder()` with `CodingErrorAction.REPORT` and catch `CharacterCodingException`.
7. **What does `ByteArrayOutputStream.toByteArray()` return?** A copy of the bytes currently written into the buffer.
8. **What does `ByteArrayOutputStream.toString(Charset)` do?** Decodes the buffer's byte contents using the specified charset.
9. **Can you call `new String(binary, UTF_8)` to preserve ZIP/image bytes intact?** No; non-text bytes can suffer data loss. Keep raw bytes or use Base64 when text representation is required.
10. **Why shouldn't you decode each network chunk independently with `new String(chunk, UTF_8)`?** A chunk boundary can split the byte sequence of a single Unicode character.
11. **Does `String.length()` equal `bytes.length`?** Not necessarily; encodings may use multiple bytes per code point.
12. **Does decoding with the wrong charset always throw an exception?** No. The result may simply be garbled text while still being a valid Unicode string.

## Java 17 API References

- [`String` constructors — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html).
- [`StandardCharsets` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).
- [`Charset` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html).
- [`CharsetDecoder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [`ByteArrayOutputStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html).
- [`Files` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [`InputStreamReader` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html).

**Key takeaway:** `byte[]` is just raw bytes; textual meaning emerges only when you apply the right charset. Use `new String(bytes, charset)` for valid text data, `new String(bytes, offset, length, charset)` for an exact byte slice, and `CharsetDecoder` with `REPORT` when invalid bytes must be rejected rather than silently replaced.
