# Verifying Exact Byte Content and Text Round-Trips in Java I/O

When testing file read/write operations, stream copying, text encoding/decoding, or socket communication, a "no exception" outcome **is not enough to prove the data is correct**. An I/O operation can complete while dropping the last byte, adding a BOM, converting `\n` to `\r\n`, using the wrong charset, replacing unmappable characters, or unintentionally normalizing text. Such bugs may not be obvious when merely opening the file in an editor.

This lesson distinguishes between **byte-for-byte verification** and **text round-trip verification**; it guides you in designing assertions, golden fixtures, diagnostics with hexadecimal dumps and mismatch offsets, and using `Arrays.equals`, `Arrays.mismatch`, `Files.mismatch`, `HexFormat`, `StandardCharsets`, and `CharsetDecoder`/`CharsetEncoder` in Java 17+. The goal is not just checking whether data can be "read back", but knowing **which property you are proving, where information can be lost, and how to inspect discrepancies**.

## 1. Three Correctness Requirements Often Confused

Distinguish between these three questions:

| Requirement | What Must Be Compared | Examples |
| --- | --- | --- |
| **Byte exactness** | The entire source byte sequence and target byte sequence must match byte-for-byte, in the same order, with the same length. | Copying binary files, transferring bytes from network to file, storing immutable artifacts. |
| **Text round-trip** | The original `String` text, after encode → write → read → decode, must match the original text according to the **chosen comparison criteria**. | Saving and reading back UTF-8 text. |
| **Logical equivalence** | Two objects/texts have the same meaning under a schema or canonicalization rule, even though raw bytes may differ. | JSON with different spacing, Unicode NFC/NFD, files with LF/CRLF per policy. |

These three properties do not imply one another. Text may "look right" when read back even though the bytes differ; conversely, two byte-identical files do not prove the content is valid UTF-8 or conforms to a business schema.

Diagram:

```text
Original String
      |
      | encode(StandardCharsets.UTF_8)
      v
Expected Bytes ------ compare byte-for-byte ------> Bytes read from file
      |                                               |
      | write                                         | decode(UTF-8)
      v                                               v
  File / stream                                 Decoded String
                                                      |
                                             String.equals(original)
```

**Test design rule:** Before writing an assertion, decide whether you need **byte exactness**, **text equality**, or **logical equivalence**. Never substitute a weaker criterion simply because it is easier to test.

## 2. What Does Byte-for-Byte Mean?

Given two byte sequences `A` and `B`, they are equal byte-for-byte when:

1. `A.length == B.length`; and
2. For every index `i` from 0 to length - 1, `A[i] == B[i]`.

Even a single-byte difference must cause the test to fail:

```text
Expected:  41 42 43 0a          "ABC\n" UTF-8
Actual:    41 42 43 0d 0a       "ABC\r\n" UTF-8
                     ^
                Differs starting at index 3.
```

Do not test binary copying with `String.equals` or `Files.readString`: PNG files, ZIP archives, protobuf payloads, or ciphertext are not character strings. Decoding binary bytes and re-encoding them can alter the data, even without throwing an exception.

For small data in tests:

```java
byte[] expected = {0x00, 0x01, (byte) 0xFF};
byte[] actual   = Files.readAllBytes(path);

if (!Arrays.equals(expected, actual)) {
    throw new AssertionError("Bytes differ");
}
```

This is a **snippet** with `path` declared externally, requiring imports for `java.nio.file.Files` and `java.util.Arrays`. The cast `(byte) 0xFF` is needed because Java's `byte` is a signed type (-128..127), whereas on disk it is still stored as the unsigned byte `FF`.

A common pitfall: `Arrays.toString(byte[])` prints signed numbers, e.g. byte `FF` becomes `-1`. When analyzing at the byte level, print hexadecimal using `HexFormat` or use `Byte.toUnsignedInt(byte)`.

## 3. `Arrays.equals`, `Arrays.mismatch`, and `Files.mismatch`

Three APIs for quick verification:

| API | Input | Output | When Appropriate |
| --- | --- | --- | --- |
| `Arrays.equals(byte[], byte[])` | Two arrays in RAM | `boolean` | Small fixtures where data is already fully loaded. |
| `Arrays.mismatch(byte[], byte[])` | Two arrays in RAM | First differing index, or `-1` if equal | Diagnosing the mismatch position; if one array is a prefix of the other, the index is the length of the shorter array. |
| `Files.mismatch(Path, Path)` | Two files | 0-based byte offset of the first mismatch, or `-1L` if equal | Comparing files directly, avoiding hand-written `readAllBytes` loops for large files. |

Example:

```java
byte[] expected = {1, 2, 3, 4};
byte[] actual = {1, 2, 9, 4};

System.out.println(Arrays.equals(expected, actual));  // false
System.out.println(Arrays.mismatch(expected, actual)); // 2
```

This is a snippet. `Arrays.mismatch` and `Files.mismatch` have been available since JDK releases prior to Java 17 and work in Java 17+. `Files.mismatch` can throw `IOException`; if a file is being modified by another process during the check, the result may not reflect a stable snapshot.

**Note on `Files.mismatch`:** Returns `-1L` when byte contents match; returns a **0-based** offset when they differ. If files only differ by trailing data, the result equals the position right after the last byte of the shorter file.

Do not compare only `Files.size(source) == Files.size(target)`: two files with different contents can have the exact same byte count. Do not compare only timestamps or file names. To prove all bytes match, use an actual byte comparison or a source/target digest suited to your threat model.

## 4. Diagnostics with Hex, Offset, and Context

If a test only reports `expected != actual`, debugging is difficult when a file is several MBs long. Report:

- The file path or ID (filtered so sensitive information is not exposed).
- Total expected/actual lengths.
- **The 0-based offset of the first differing byte**.
- A hex window around the offset, e.g. 16 bytes before and after.
- Relevant charset/encoding, newline, and BOM policies.
- A note indicating that the dump shows raw bytes, not "similar-looking" characters.

Java 17 provides `HexFormat`:

```java
byte[] bytes = {(byte) 0xEF, (byte) 0xBB, (byte) 0xBF};
System.out.println(HexFormat.of().formatHex(bytes)); // efbbbf
byte[] reconstructed = HexFormat.of().parseHex("efbbbf");
```

This snippet requires importing `java.util.HexFormat`. For sensitive data (tokens, private keys, personal information), **never** log raw hex dumps just for debugging: hex still reveals the data. Log offsets, lengths, and non-secret digests per policy; only dump bytes when permitted and with redaction in place.

Example helper producing a structured error:

```java
static void assertExact(byte[] expected, byte[] actual) {
    int mismatch = Arrays.mismatch(expected, actual);
    if (mismatch >= 0) {
        throw new AssertionError(
                "Byte mismatch at offset=" + mismatch
                + "; expectedLength=" + expected.length
                + "; actualLength=" + actual.length);
    }
}
```

This is a snippet inside a class importing `java.util.Arrays`. In tests, this helper can be replaced by JUnit 5's `assertArrayEquals`, adding hex context when a case fails.

## 5. The Charset Must Be Explicitly Specified

When converting between `String` and bytes, the charset is part of the data contract:

```java
String original = "Tiếng Việt";
byte[] data = original.getBytes(StandardCharsets.UTF_8);
String restored = new String(data, StandardCharsets.UTF_8);

if (!original.equals(restored)) {
    throw new AssertionError("Text round-trip failed");
}
```

This is a snippet; `StandardCharsets.UTF_8` supplies an explicit charset. Avoid overloads like `str.getBytes()` or `new String(bytes)` when the data format must persist or move across machines: the default charset depends on the environment/JDK. Especially on Java 17 and earlier JDKs before Java 18's default charset change, the same code without an explicit charset can process bytes differently across machines.

Common charsets:

| Charset | Contract | Risk When Misused |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | Variable-length Unicode, the right default choice for new text data. | Decoding with another charset causes mojibake or errors. |
| `StandardCharsets.US_ASCII` | Encodes only the basic ASCII set. | Characters like `đ`, `é`, and emoji cannot be represented. |
| `StandardCharsets.ISO_8859_1` | Single byte for code values 0–255 in that code page. | Does not cover Vietnamese or emoji. |
| `UTF_16LE`/`UTF_16BE` | Encodes UTF-16 code units with explicit byte order. | Wrong endianness or BOM protocol corrupts text. |

**You cannot infer byte exactness solely from** `String.equals`. If code decoded bytes incorrectly under a policy that replaces invalid bytes with a replacement character, string comparison still cannot recover or verify the original bytes.

## 6. "Text Round-Trip" Has Two Directions to Test Separately

### Direction A: String → encode → decode → String

For a valid Java string whose characters are fully representable by the charset and without transformation steps, we expect:

```text
originalText == decode(encode(originalText, charset), charset)
```

With UTF-8 and valid Unicode data, this normally preserves the string exactly. However, a Java string can contain an **unpaired surrogate**, which is not a valid Unicode scalar value; if an encoder uses a replacement policy, the round-trip **can lose information**. Choose error-reporting mode when the format requires strict encoding.

### Direction B: raw bytes → decode → encode → raw bytes

This direction is stronger:

```text
originalBytes == encode(decode(originalBytes, charset), charset)
```

It holds only when the byte sequence is valid and decoding/re-encoding under the protocol produces a unique corresponding byte representation. With invalid UTF-8, corrupted encodings, charsets with multiple representations, replacement policies, or canonicalization, there is no guarantee raw bytes are reproduced.

**Test both directions when both are actually required**. For binary files with no text-decoding requirement, compare bytes only. For documents normalized per policy, verify logical equivalence instead of demanding byte exactness.

## 7. Standalone Java 17+ Example: File Bytes, UTF-8 Round-Trip, and Pitfalls

This program creates temporary files, writes text containing Vietnamese, emoji, and newlines. It copies the file, verifies bytes using `Arrays.equals` and `Files.mismatch`, then reads the text and re-encodes it. The example also checks UTF-8 bytes of `é`, compares Unicode normalization, line endings, and rejection of malformed UTF-8.

Save with exact name **`ByteExactRoundTripDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.HexFormat;

public class ByteExactRoundTripDemo {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("roundtrip-source-", ".txt");
        Path copy = Files.createTempFile("roundtrip-copy-", ".txt");
        try {
            String text = "Tiếng Việt 😀\nDòng 2";
            byte[] expected = text.getBytes(StandardCharsets.UTF_8);

            Files.write(source, expected);
            Files.copy(source, copy,
                    java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            byte[] actual = Files.readAllBytes(copy);

            check(Arrays.equals(expected, actual), "Bytes changed");
            check(Files.mismatch(source, copy) == -1, "Files differ");

            String decoded = Files.readString(copy, StandardCharsets.UTF_8);
            check(text.equals(decoded), "Text changed");
            check(Arrays.equals(expected,
                    decoded.getBytes(StandardCharsets.UTF_8)),
                    "Re-encoding changed bytes");

            System.out.println("bytes-equal=true");
            System.out.println("files-mismatch=-1");
            System.out.println("text-roundtrip=true");
            System.out.println("reencode-equal=true");
            System.out.println("utf8-accent=" + HexFormat.of().formatHex(
                    "é".getBytes(StandardCharsets.UTF_8)));

            String composed = "café";
            String decomposed = "cafe\u0301";
            System.out.println("nfc-nfd-byte-equal=" + Arrays.equals(
                    composed.getBytes(StandardCharsets.UTF_8),
                    decomposed.getBytes(StandardCharsets.UTF_8)));
            System.out.println("nfc-nfd-normalized-equal=" +
                    Normalizer.normalize(composed, Normalizer.Form.NFC)
                            .equals(Normalizer.normalize(
                                    decomposed, Normalizer.Form.NFC)));

            System.out.println("lf-crlf-byte-equal=" + Arrays.equals(
                    "A\nB".getBytes(StandardCharsets.UTF_8),
                    "A\r\nB".getBytes(StandardCharsets.UTF_8)));

            boolean rejected = false;
            try {
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(
                                new byte[] {(byte) 0xC3, (byte) 0x28}));
            } catch (CharacterCodingException expectedError) {
                rejected = true;
            }
            check(rejected, "Malformed UTF-8 was accepted");
            System.out.println("malformed-rejected=true");
        } finally {
            Files.deleteIfExists(copy);
            Files.deleteIfExists(source);
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 ByteExactRoundTripDemo.java
java ByteExactRoundTripDemo
```

Stdout verified by compiling and running:

```text
bytes-equal=true
files-mismatch=-1
text-roundtrip=true
reencode-equal=true
utf8-accent=c3a9
nfc-nfd-byte-equal=false
nfc-nfd-normalized-equal=true
lf-crlf-byte-equal=false
malformed-rejected=true
```

**Step-by-step explanation:**

1. `text` contains Vietnamese and a supplementary-plane emoji; `text.getBytes(UTF_8)` produces bytes with an explicit encoding.
2. `Files.write(source, expected)` writes the original bytes; `Files.copy` copies them to another temporary file. `Arrays.equals` compares byte arrays; `Files.mismatch == -1` confirms both files have identical byte content.
3. `Files.readString(copy, UTF_8)` reads the text. `String.equals` checks the sequence of UTF-16 code units; re-encoding verifies identical bytes in this valid UTF-8 case.
4. `"é"` in UTF-8 is `C3 A9`; `HexFormat` yields `c3a9`.
5. `"café"` uses precomposed `é`, whereas `"cafe\u0301"` uses `e` + combining acute accent. The bytes differ, but after `Normalizer.normalize(..., NFC)` they compare equal.
6. `"A\nB"` and `"A\r\nB"` differ in bytes: `0A` vs `0D 0A`. Editors may render both files identically, so text rendering is insufficient to prove byte equality.
7. The byte sequence `C3 28` is invalid UTF-8. `CharsetDecoder` with `CodingErrorAction.REPORT` throws an error so tests catch it instead of silently replacing it with `U+FFFD`.
8. `finally` cleans up both temporary files. The demo uses small data; for very large files, avoid `Files.readAllBytes` to limit memory usage.

**Key takeaway:** This example proves **three independent claims**: intact byte copying, accurate text round-trip when the charset matches, and strict decoder rejection of invalid input. Never use the result of one claim as a substitute assertion for another.

## 8. Checking Bytes After `FileChannel` or Stream Partial I/O

With `InputStream.read(buffer)`, the return value is the number of bytes **actually read**, or `-1` at EOF. Never assume a single `read` fills the array, especially when reading from sockets, pipes, or large streams.

When copying in chunks, the rule is:

```java
// Snippet: in and out are open InputStream/OutputStream instances.
byte[] buf = new byte[8192];
for (int n; (n = in.read(buf)) != -1; ) {
    out.write(buf, 0, n);
}
```

This is a snippet; `IOException` handling and `try-with-resources` are needed at the caller. With a regular `InputStream`, `read(byte[])` may return fewer bytes than `buf.length`; calling `out.write(buf)` instead of `out.write(buf, 0, n)` would write stale bytes from the tail of the array.

With `FileChannel` and `ByteBuffer`:

```java
// Snippet: source and target are FileChannel instances,
// buffer has capacity > 0.
while (true) {
    int n = source.read(buffer);
    if (n == -1) {
        break;
    }
    if (n == 0) {
        throw new IOException("Reading made no progress");
    }
    buffer.flip();
    while (buffer.hasRemaining()) {
        if (target.write(buffer) == 0) {
            throw new IOException("Writing made no progress");
        }
    }
    buffer.clear();
}
```

This is a fail-fast pattern for blocking file channels in an application-controlled context; **do not** copy the `n == 0` policy verbatim to a non-blocking `SocketChannel`, where you must wait for readiness rather than throwing an error. Verifying after copying with `Files.mismatch` or a reliable digest is more meaningful in practice than only checking the byte count passed to `write`.

If code uses `ByteBuffer.array()`, note that the backing array may be larger than the valid data region, and direct/read-only/sliced buffers may not support `array()`. Use `position/limit/remaining` or properly bounded views; do not assume the entire array is always payload.

## 9. Characters, Code Points, UTF-16 Code Units, and Byte Counts

A Java `String` is a sequence of **UTF-16 code units**. Therefore:

- `String.length()` returns the number of code units, not Unicode code points and not UTF-8 bytes.
- A supplementary character, such as `😀`, takes **two UTF-16 code units** and typically **four UTF-8 bytes**.
- A precomposed `é` character is typically one code unit and two UTF-8 bytes.
- Combining characters can form one visual glyph from multiple code points/code units; the number of displayed glyphs does not equal `String.length()`.

Illustrative example:

```java
String emoji = "😀";
System.out.println(emoji.length()); // 2 UTF-16 code units
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
System.out.println(emoji.getBytes(StandardCharsets.UTF_8).length); // 4
```

This is a snippet. If a protocol specifies a header containing payload length **in bytes**, use `data.length` of the encoded byte array, never `str.length()`. In binary protocols, using the wrong byte count leads to truncated payloads or reading past into subsequent data.

If you need to iterate Unicode code points, consider `String.codePoints()`, though even the code point count does not always equal the number of user-perceived grapheme clusters. For byte-exact comparisons, the proper unit remains the **byte sequence**.

## 10. Unicode Normalization: "Looks the Same" Does Not Mean `String.equals`

Example representations of an accented character:

```text
NFC / composed: "é"           U+00E9        UTF-8 C3 A9
NFD / decomposed: "e◌́"        U+0065 U+0301 UTF-8 65 CC 81
```

Two strings can look identical in a UI yet have different bytes, and Java's `String.equals` will also typically return false because their UTF-16 code units differ. If business logic requires treating them as equivalent under Unicode canonical equivalence, an explicit **normalization rule** is needed:

```java
String left = Normalizer.normalize(sourceText, Normalizer.Form.NFC);
String right = Normalizer.normalize(restoredText, Normalizer.Form.NFC);
boolean sameMeaningByPolicy = left.equals(right);
```

This is a snippet with `import java.text.Normalizer;` and application-provided string variables. Prefer **NFC** when a product requires canonical normalization, but normalization is not always harmless: when verifying raw files, digital signatures, protocol bytes, file paths, or data requiring byte-exactness, normalization alters bytes and **must not be performed implicitly**.

The forms `NFC`, `NFD`, `NFKC`, and `NFKD` serve different purposes; compatibility normalization such as NFKC can alter the visual appearance or meaning of certain compatible characters. Choose according to the contract, not as a default way to "fix encoding bugs".

## 11. Line Endings and APIs That Erase Line Boundaries

Three common line ending forms:

| Form | Hex | Usage |
| --- | --- | --- |
| LF | `0A` | Common in Unix/Linux environments and many protocols. |
| CRLF | `0D 0A` | Common on Windows and several network protocols. |
| CR | `0D` | Exists in legacy data or specific proprietary formats. |

`BufferedReader.readLine()` returns line contents **without line terminators**. Therefore, reading lines with `readLine()` and writing them back with `writer.newLine()` can alter the bytes of the original file:

- A file has `\n`, but the target machine produces `\r\n`.
- Whether the file ended with a trailing newline or not may be lost.
- Mixed newline styles within the same file are not preserved.
- Standalone CR/LF boundaries may be handled according to the reader's policy.

Similarly, high-level line APIs like `Files.readAllLines` and `Files.lines` are suitable for processing **line-by-line content**, not for testing byte-for-byte preservation of line breaks.

When preserving files verbatim, process at the byte level or preserve exact line separators. When business rules require normalizing line endings, write separate tests proving the **normalized result** and clearly label it an intentional transformation rather than a raw byte round-trip.

## 12. BOM and Invisible Bytes at the Start of a File

Some text files contain a **Byte Order Mark (BOM)**. For example, the UTF-8 BOM is three bytes:

```text
EF BB BF
```

UTF-8 does not need a BOM to determine byte order; however, some software still creates UTF-8 files with a BOM. Two files with the exact same visible characters where one has a BOM and the other does not **will differ in SHA-256, size, and byte exactness**.

Points that must be defined:

1. Does the protocol allow a BOM?
2. Should the parser detect/strip the BOM, or treat it as a `U+FEFF` code point?
3. Should the writer always add a BOM, never add a BOM, or copy verbatim?
4. Which endianness does UTF-16 use; is there a BOM or are `UTF_16LE`/`UTF_16BE` explicitly specified?

If byte exactness is required, **the BOM is data to verify like any other byte**. If semantic text round-trip is required, both sides must agree on the BOM rule before comparing strings. Never add or strip a BOM silently just because one OS editor handles it differently.

## 13. Strict Decoding and Invalid Data Errors

Some convenience APIs handle malformed input with a **replacement character**, resulting in silent data loss. When a format requires exact UTF-8, use a decoder with `CodingErrorAction.REPORT`:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    CharBuffer result = decoder.decode(ByteBuffer.wrap(bytes));
    String restored = result.toString();
} catch (CharacterCodingException invalid) {
    throw new IOException("Malformed UTF-8 input", invalid);
}
```

This is a snippet requiring imports for `java.nio.ByteBuffer`, `java.nio.CharBuffer`, `java.nio.charset.CharsetDecoder`, `java.nio.charset.CodingErrorAction`, `java.nio.charset.CharacterCodingException`, and appropriate variables.

**Malformed** typically refers to a structurally invalid byte sequence for the encoding; **unmappable** refers to valid input that has no valid character representation in the target charset. In UTF-8, a malformed example is `C3 28`: byte `C3` expects a valid continuation byte, but the next byte is `28`.

Similarly, when encoding text into a charset that cannot represent all characters:

```java
CharsetEncoder strictAscii = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
try {
    ByteBuffer encoded = strictAscii.encode(CharBuffer.wrap("Tiếng Việt"));
} catch (CharacterCodingException unsupported) {
    // Data contains characters not representable in ASCII.
}
```

This is a snippet. `String.getBytes(Charset)` can replace unmappable characters or malformed sequences with replacement bytes per the API, so to **detect invalid data** instead of silently replacing it, use a strict `CharsetEncoder` as shown above. Avoid accidental "passing tests" where both the writer and reader used the same lossy replacement policy.

## 14. Golden Fixtures and Mandatory Test Cases

Good tests do not merely round-trip through the same encode/decode functions; if both share the same bug, they can validate each other falsely. You need **golden bytes independent** of the code under test.

Recommended fixture set:

| Fixture | Characteristic Bytes or Content | What Defect It Catches |
| --- | --- | --- |
| Empty file | Zero bytes. | Unexpected BOM/newline/header added. |
| Short ASCII | `abc` = `61 62 63` | Basic data and content length. |
| Null byte | `00` inside payload. | Not treating null as a C-style string terminator. |
| High bytes | `80 FF` | Signed byte issues, no accidental text decoding. |
| UTF-8 Vietnamese diacritics | `đ, ế, ộ` | Wrong charset / replacement. |
| Supplementary emoji | `😀` | Surrogate pairs and byte count. |
| NFC vs NFD | `C3 A9` vs `65 CC 81` | Visual equality does not imply byte equality. |
| LF and CRLF | `0A` vs `0D 0A` | Line ending rewrites. |
| With/without BOM | `EF BB BF` before text | BOM policy. |
| Malformed UTF-8 | `C3 28` or truncated multibyte | Strict decoder must reject. |
| Unpaired UTF-16 surrogate | E.g. a high surrogate without a low surrogate | Strict encoder must reject. |
| Multiple chunks | Data larger than buffer, short final chunk | Partial reads and stale bytes. |
| Real binary file | Small verified PNG/ZIP fixture | Not using `String` as an intermediary. |
| Large file | Multiple MiB/GB per test infrastructure | Streaming, memory, timeout, safeguard policies. |

For hex-defined fixtures, construct expected bytes using `HexFormat.parseHex` from a reviewed string or protocol standard. Avoid generating expected bytes using the very encode API under test and then claiming the encoding is verified.

## 15. JUnit 5 Example: Exact Assertions (JUnit-Dependent Snippet)

In a project with JUnit Jupiter configured, you can use:

```java
import static org.junit.jupiter.api.Assertions.*;

byte[] expected = HexFormat.of().parseHex("61c3a90a");
byte[] actual = "aé\n".getBytes(StandardCharsets.UTF_8);
assertArrayEquals(expected, actual);

String text = "Tiếng Việt 😀";
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
assertEquals(text, new String(encoded, StandardCharsets.UTF_8));
```

This is a **JUnit 5 snippet**, not a standalone program. It assumes imports for `HexFormat` and `StandardCharsets`, running inside a test method with the appropriate `org.junit.jupiter:junit-jupiter` dependency.

To diagnose mismatches:

```java
int offset = Arrays.mismatch(expected, actual);
assertEquals(-1, offset,
        () -> "Mismatch at byte index " + offset
                + "; expectedHex=" + HexFormat.of().formatHex(expected)
                + "; actualHex=" + HexFormat.of().formatHex(actual));
```

This is another test snippet; do not print sensitive payloads in messages. JUnit's `assertArrayEquals` is usually convenient for array equality, while `mismatch` is useful when you want to report the exact offset.

For large files, avoid embedding entire files in assertion messages. Separate integration tests comparing with `Files.mismatch`, recording sizes, the first mismatch offset, and bounded context logs.

## 16. Round-Tripping with `Reader`/`Writer` and `CharsetDecoder`

If an application genuinely reads and writes **text**, `Reader`/`Writer` APIs are appropriate because they operate on characters rather than bytes. However, tests must recognize that reading text and writing it back **re-encodes the data**:

```java
// Snippet: source and target are controlled Paths.
try (BufferedReader reader = Files.newBufferedReader(
         source, StandardCharsets.UTF_8);
     BufferedWriter writer = Files.newBufferedWriter(
         target, StandardCharsets.UTF_8)) {
    char[] chars = new char[4096];
    int n;
    while ((n = reader.read(chars)) != -1) {
        writer.write(chars, 0, n);
    }
}
```

This is a snippet requiring imports for `BufferedReader`, `BufferedWriter`, `Files`, `StandardCharsets`, and `IOException` handling. Note the difference between copying **char arrays** and copying **line by line**: continuous char read/write can preserve decoded newline characters, whereas `readLine`/`newLine` can alter them.

Yet using `Reader`/`Writer` still does **not** automatically guarantee byte-exactness: decoders/encoders can handle BOMs, malformed input, replacements, charsets, or canonicalization differently. When the original bytes are canonical data that must stay untouched, copy at the byte layer first and verify with file mismatch.

For long encoded streams, low-level `CharsetDecoder.decode(ByteBuffer, CharBuffer, boolean)` maintains incremental state to handle characters split across two chunks; never call `new String(chunk, UTF_8)` independently on every byte slice received from a socket because a multibyte character may be split across chunks.

## 17. Diagnosing Unicode Split Across Chunks

UTF-8 encodes `é` as:

```text
Chunk 1: C3
Chunk 2: A9
Full stream: C3 A9  -> U+00E9
```

If you write:

```java
String a = new String(new byte[] {(byte) 0xC3},
        StandardCharsets.UTF_8);
String b = new String(new byte[] {(byte) 0xA9},
        StandardCharsets.UTF_8);
String result = a + b;
```

that is **not** a valid decoding of the full `C3 A9` sequence. Each chunk is invalid on its own and convenience decoders may produce replacement characters.

The right approaches:

- For small data, **accumulate bytes** until the complete message arrives, then decode once.
- For large streams, use `InputStreamReader`/`BufferedReader` reading continuously from the stream so the decoder preserves state across internal buffer boundaries.
- Or drive an incremental `CharsetDecoder` with `CoderResult`, `endOfInput` state, `flush()`, and a buffer using `compact()` when incomplete UTF-8 bytes remain.

If a protocol parser frames messages by **byte length**, first verify all frame bytes have arrived before decoding; never add `String.length()` as the byte count in a header.

## 18. Handling Large Files Without Unbounded RAM Usage

Convenience APIs such as `Files.readAllBytes` and `Files.readString` are very useful for **unit tests with small fixtures**. For large files, loading all bytes/text into RAM can exhaust the heap, trigger long GC pauses, or cause tests not to reflect production streaming code.

Strategies:

1. **File-to-file exact check:** Use `Files.mismatch(pathA, pathB)` to get the first mismatch offset.
2. **Streaming compare:** Open two input streams; read in chunks, compare valid content per read, while handling size differences and partial reads.
3. **Streaming hash:** When verifying against a trusted reference digest, compute SHA-256 via `MessageDigest`/`DigestInputStream` without retaining all bytes.
4. **Small golden fixtures:** For protocol serializers, choose test vectors covering boundary cases rather than multi-GB files.
5. **Boundary tests:** Sizes 0, 1, bufferSize-1, bufferSize, bufferSize+1, multiples of bufferSize+1; specifically test a short final chunk.
6. **Resource closure:** Use `try-with-resources` for streams/channels and handle close errors.
7. **Concurrency:** If the source is being modified by another process, comparison/hashing may not correspond to a consistent snapshot. Isolate immutable sources, use snapshots, or coordinate with the writer before checking.

Do not use `MessageDigest.isEqual` to "replace file content comparison" when both digests are computed on the fly from files that could be modified concurrently and the application must guarantee a specific version. Digest comparison is appropriate when the input is read stably and trust/reference criteria are clearly defined.

## 19. Common Bugs and Root Causes

| Symptom | Root Cause | Resolution |
| --- | --- | --- |
| Test passes even with trailing garbage bytes | Comparing strings after trim, or comparing only prefixes. | Check byte length and all bytes via `Arrays.equals`/`Files.mismatch`. |
| Text looks identical in editor but mismatches | Different BOM, line endings, Unicode normalization, or invisible whitespace. | Print hex/offset, inspect raw bytes first. |
| Emoji breaks byte length | Using `String.length()` as UTF-8 byte count. | Encode first and use `byte[].length`. |
| Only the last chunk is corrupted | Writing the entire buffer instead of only the `n` newly read bytes. | Use `write(buffer, 0, n)` or set `ByteBuffer.limit` properly. |
| Byte `FF` prints as `-1` | Java `byte` is signed. | Use `Byte.toUnsignedInt` and hex. |
| Wrong charset only on another machine | Relying on default charset instead of specifying it explicitly. | Use `StandardCharsets.UTF_8` consistently. |
| Corrupted text decoding doesn't fail tests | Decoder silently replaces invalid input. | Use `CharsetDecoder` with `CodingErrorAction.REPORT`. |
| ASCII encoding still "works" on Vietnamese text | Encoder replaces unmappable characters. | Use strict `CharsetEncoder` and assert failure. |
| Text converted `LF → CRLF` | `BufferedReader.readLine` followed by `newLine()`. | Copy bytes or preserve line endings per policy. |
| Data lost when decoding stream in chunks | Multibyte UTF-8 split across two reads. | Stateful streaming decoder or proper accumulation. |
| Hash matches but file is wrong version | Reference hash not bound to identity/version. | Trusted manifest containing algorithm, path, version, digest. |
| Copying via text API corrupts ZIP | Attempting to decode binary bytes into a `String`. | Use `InputStream`/`OutputStream` or `FileChannel`. |
| Tests non-reproducible on CI | Dependent on locale, timezone, EOL, default charset, or path separator. | Deterministic fixtures and explicit configuration. |
| File being written concurrently makes test flaky | Comparing without snapshot while file changes during read. | Ensure file is immutable or copy/snapshot before verifying. |
| Logging full hex dumps for debugging | Leaks sensitive data or bloats logs. | Log only offset and bounded context window when permitted. |

## 20. Designing a Reliable Test Suite

A solid suite should span multiple layers:

**Encoder/decoder unit tests:** Verify independent golden bytes; test valid and invalid UTF-8; assert failures on unpaired surrogates or malformed byte sequences; verify explicit charsets rather than defaults.

**Read/write helper tests:** Use bytes containing `00`, `FF`, deterministically seeded random data, and sizes spanning multiple buffer boundaries; verify exact bytes after a copy round-trip.

**Text round-trip tests:** Test Vietnamese, emoji, combining marks, line breaks, trailing empty lines, and BOM policies; decide explicitly whether the test expects exact `String.equals` or normalization equivalence.

**Integration tests:** Write files, close resources, reopen from disk, compare with `Files.mismatch`, check behavior on Windows/Linux where needed; document any OS-dependent assumptions.

**Regression tests:** Every encoding/copying bug discovered should get a fixture reproducing the exact broken bytes. Never "update" expected output to make a test pass without confirming the real data contract.

**Negative tests:** Truncated data, invalid UTF-8, unreadable files, disk full/permission errors where the test environment supports them, corrupted frames, duplicate bytes, and source modified during read; results must fail explicitly rather than falsely succeeding.

Specifically, for serializers/protocols, avoid relying solely on self-validating round-trip tests like:

```text
actualBytes = encode(input)
restored = decode(actualBytes)
assertEquals(input, restored)
```

If encode and decode share a symmetric bug, this test can still pass. Add canonical **golden byte vectors** and independent tests for both encode and decode.

## 21. Practice Exercises

**Exercise 1 — Golden UTF-8.** Use `HexFormat.parseHex("61c3a90a")` as the expected value for `"aé\n"`. Write a JUnit test comparing exact bytes with `assertArrayEquals` and explain why an independent hex fixture must be used instead of generating the expected value with the logic under test.

**Exercise 2 — Single-byte corruption.** Create a 1,024-byte `byte[]`, flip a byte at index 511, and use `Arrays.mismatch` to verify the differing position. Also test arrays of different lengths sharing a common prefix.

**Exercise 3 — BOM.** Create two UTF-8 files containing `abc`, one prefixed with `EF BB BF`. Use `Files.mismatch`, `Files.size`, and hex to report the differences. Define clearly whether a "raw exact" test and a "semantic text" test accept a BOM.

**Exercise 4 — Line endings.** Create fixtures with CRLF, LF, and mixed line endings. Copy via streams (without `readLine`) and verify byte exactness; then intentionally normalize newlines and verify the output under the new policy.

**Exercise 5 — NFC/NFD.** Compare `"café"` and `"cafe\u0301"` using `equals`, UTF-8 byte arrays, and `Normalizer.Form.NFC`. Explain why the results differ and when normalization is forbidden.

**Exercise 6 — Invalid UTF-8.** Use byte array `C3 28`. Compare strict decoder behavior with a convenience API using replacement. Ensure a pipeline requiring exact data raises an error instead of silently altering bytes.

**Exercise 7 — Split multibyte character.** Send bytes `C3 A9` across two read chunks `C3` and `A9`. Compare decoding each chunk independently versus decoding the whole stream. Fix it with `InputStreamReader` or an incremental `CharsetDecoder`.

**Exercise 8 — Large file.** Generate a seeded data file much larger than the buffer size, then copy it via `FileChannel`; assert `Files.mismatch == -1`. Inject an intentional error in a middle byte to print the mismatch offset. Do not log the full file content.

**Exercise 9 — Text length vs payload length.** Create a protocol sending `"Việt 😀"` in UTF-8 with a 4-byte length header; verify using `encoded.length`, not `String.length()`. Simulate a receiver reading the payload across multiple chunks.

**Exercise 10 — Regression fixture.** Pick a real bug such as an injected BOM or LF converted to CRLF. Save before/after fixtures in hex alongside the expected mismatch offset; write a test so the regression never returns.

### Self-Check Questions

1. Can `String.equals` prove byte-for-byte equality?
2. What does `Files.mismatch` return when two files are completely identical?
3. When a source stream reads 7 bytes into an 8,192-byte array, how many bytes should be written?
4. Why can `getBytes()` without a charset make tests unstable across environments?
5. What is `String.length()` for a supplementary emoji, and how many UTF-8 bytes does it use?
6. When do two strings display identically yet `Arrays.equals(utf8A, utf8B) == false`?
7. How does `readLine`/`newLine` affect raw line-ending bytes?
8. Why is a strict decoder necessary for text data requiring full integrity?
9. Why should you not decode partial UTF-8 bytes independently per chunk?
10. Is a passing encode→decode test suite enough to prove an encoder follows the golden wire format?

## 22. References

- [Java SE 21 — Arrays](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html): `equals`, `mismatch` for primitive arrays.
- [Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): `readAllBytes`, `readString`, `write`, `copy`, `mismatch`.
- [Java SE 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): standard available charsets.
- [Java SE 21 — CharsetDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html): detecting malformed/unmappable input.
- [Java SE 21 — CharsetEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html): error control when encoding `String` to bytes.
- [Java SE 21 — HexFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HexFormat.html): reading/writing bytes as hex.
- [Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html): Unicode normalization NFC/NFD/NFKC/NFKD.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): position/limit/remaining and NIO operations.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): assertions and data-driven tests.

**Remember:** For **byte-exact** requirements, inspect the actual bytes via `Arrays.equals`/`Arrays.mismatch`/`Files.mismatch` and report offsets on failure. For **text round-trips**, specify the charset explicitly, test both encode/decode and golden bytes, and control BOM, newlines, Unicode normalization, and malformed-input errors. "Looks right on screen" and "no exception" are no substitute for proof that content was preserved.
