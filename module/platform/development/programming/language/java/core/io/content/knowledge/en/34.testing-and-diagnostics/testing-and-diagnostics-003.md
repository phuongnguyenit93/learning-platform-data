# Checking Exact Byte Content and Text Round-Trips in Java I/O

When testing file read/write operations, stream copying, text encoding/decoding, or socket communication, "no exception thrown" **is not enough to prove the data is correct**. An I/O operation can complete while dropping the final byte, inserting a BOM, converting `\n` to `\r\n`, using the wrong charset, replacing unrepresentable characters, or inadvertently normalizing text. Such defects are often invisible when simply opening the file in an editor.

This lesson distinguishes **byte-for-byte checks** from **text round-trip checks**, and shows how to design assertions, golden fixtures, hexadecimal and mismatch-offset diagnostics, using `Arrays.equals`, `Arrays.mismatch`, `Files.mismatch`, `HexFormat`, `StandardCharsets`, and `CharsetDecoder`/`CharsetEncoder` in Java 17+. The goal is not merely verifying "it can be read back," but knowing **which property you are proving, where information can be lost, and how to diagnose mismatches**.

## 1. Three Correctness Requirements Often Confused

Distinguish these three questions:

| Requirement | What Must Be Compared | Example |
| --- | --- | --- |
| **Byte exactness** | The entire source byte sequence and target byte sequence must match byte for byte, in the same order and length. | Copying binary files, transferring bytes from network to file, storing immutable artifacts. |
| **Text round-trip** | The original `String`, after encode → write → read → decode, must match the original text under the **chosen comparison criteria**. | Saving and reading back UTF-8 text. |
| **Logical equivalence** | Two objects/texts carry the same meaning under a schema or canonicalization rule, even if raw bytes differ. | JSON with different spacing, Unicode NFC/NFD, files using LF/CRLF by policy. |

These three properties do not automatically imply one another. Text may "look right" when read back even though the bytes changed; conversely, two byte-identical files do not prove the content is valid UTF-8 or conforms to a business schema.

Diagram:

```text
Original String
      |
      | encode(StandardCharsets.UTF_8)
      v
Expected bytes ----- byte-for-byte comparison ----> Bytes read from file
      |                                               |
      | write                                         | decode(UTF-8)
      v                                               v
  File / stream                                 Decoded String
                                                      |
                                             String.equals(original)
```

**Test design rule:** before writing an assertion, decide whether you need **byte exactness**, **text equality**, or **logical equivalence**. Never substitute a weaker criterion simply because it is easier to test.

## 2. What Does Byte-for-Byte Mean?

Given two byte sequences `A` and `B`, they are byte-for-byte equal when:

1. `A.length == B.length`; and
2. For every index `i` from `0` to `length - 1`, `A[i] == B[i]`.

Even a single-byte difference must fail the test:

```text
Expected:  41 42 43 0a          "ABC\n" UTF-8
Actual:    41 42 43 0d 0a       "ABC\r\n" UTF-8
                     ^
            Differs starting at index 3.
```

Do not test binary copying with `String.equals` or `Files.readString`: PNG, ZIP, protobuf, or ciphertext files are not character strings. Decoding binary bytes and re-encoding them can alter the data even without throwing an exception.

For small data in tests:

```java
byte[] expected = {0x00, 0x01, (byte) 0xFF};
byte[] actual   = Files.readAllBytes(path);

if (!Arrays.equals(expected, actual)) {
    throw new AssertionError("Bytes differ");
}
```

This is a **snippet** with `path` declared externally, requiring imports for `java.nio.file.Files` and `java.util.Arrays`. Cast `(byte) 0xFF` because Java `byte` is signed (-128..127), though the file representation is still the unsigned byte `FF`.

A common pitfall: `Arrays.toString(byte[])` prints signed numbers, so byte `FF` appears as `-1`. When analyzing at the byte level, print hexadecimal with `HexFormat` or use `Byte.toUnsignedInt(byte)`.

## 3. `Arrays.equals`, `Arrays.mismatch`, and `Files.mismatch`

Three APIs provide fast verification:

| API | Input | Output | When Appropriate |
| --- | --- | --- | --- |
| `Arrays.equals(byte[], byte[])` | Two arrays in RAM | `boolean` | Small fixtures and data already fully read. |
| `Arrays.mismatch(byte[], byte[])` | Two arrays in RAM | First differing index, or `-1` if equal | Diagnosing mismatch position; if one array is a prefix of the other, returns the length of the shorter array. |
| `Files.mismatch(Path, Path)` | Two files | First differing byte offset, or `-1L` if equal | Comparing files directly, avoiding manual `readAllBytes` loops on large files. |

Example:

```java
byte[] expected = {1, 2, 3, 4};
byte[] actual = {1, 2, 9, 4};

System.out.println(Arrays.equals(expected, actual));  // false
System.out.println(Arrays.mismatch(expected, actual)); // 2
```

This is a snippet. `Arrays.mismatch` and `Files.mismatch` have existed since JDK versions prior to Java 17 and work in Java 17+. `Files.mismatch` can throw `IOException`; if another process modifies a file during comparison, the result may not reflect a stable snapshot.

**Special note on `Files.mismatch`:** returns `-1L` when byte contents are identical; returns a **0-based** offset when they differ. For files differing only by trailing bytes, the result equals the position right after the last byte of the shorter file.

Do not just compare `Files.size(source) == Files.size(target)`: two files with different content can have the same byte count. Do not compare only timestamps or file names. To prove all bytes match, use real byte comparison, or source-and-target digests suited to your threat model.

## 4. Diagnostics with Hex, Offsets, and Context

If a test merely reports `expected != actual`, debugging a multi-megabyte file is painful. Instead report:

- File path or identifier (redacted so sensitive information is not leaked).
- Expected and actual total lengths.
- **First mismatching byte offset**, 0-based.
- A hex window around the offset, such as 16 bytes before and after.
- Relevant charset/encoding, newline, and BOM policy.
- A clear note that the dump shows raw bytes, not visually similar characters.

Java 17 includes `HexFormat`:

```java
byte[] bytes = {(byte) 0xEF, (byte) 0xBB, (byte) 0xBF};
System.out.println(HexFormat.of().formatHex(bytes)); // efbbbf
byte[] reconstructed = HexFormat.of().parseHex("efbbbf");
```

This snippet requires importing `java.util.HexFormat`. For sensitive data (tokens, private keys, personal data), **never** log raw hex dumps just for debugging: hex still exposes the data. Log offsets, lengths, and non-secret digests per policy; only dump bytes when permitted and redacted.

Example helper producing structured error output:

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

This is a snippet inside a class importing `java.util.Arrays`. In tests, this helper can be replaced with JUnit 5 `assertArrayEquals` supplemented with hex context when a case fails.

## 5. Charset Must Be Specified Explicitly

When converting between `String` and bytes, the charset is part of the data contract:

```java
String original = "Tiếng Việt";
byte[] data = original.getBytes(StandardCharsets.UTF_8);
String restored = new String(data, StandardCharsets.UTF_8);

if (!original.equals(restored)) {
    throw new AssertionError("Text round-trip failed");
}
```

This is a snippet; `StandardCharsets.UTF_8` supplies the explicit charset. Avoid overloads like `str.getBytes()` or `new String(bytes)` when the data format must persist or move across machines: the default charset depends on the environment/JDK. Especially on Java 17 and JDK versions before Java 18's default-charset change, code without an explicit charset can process bytes differently across machines.

Some common charsets:

| Charset | Contract | Risk When Misused |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | Variable-length Unicode, the right default choice for modern text data. | Decoding with another charset causes mojibake or errors. |
| `StandardCharsets.US_ASCII` | Encodes only basic ASCII characters. | Characters like `đ`, `é`, and emojis cannot be represented. |
| `StandardCharsets.ISO_8859_1` | Single byte for values 0–255 of that code page. | Cannot represent full Vietnamese text or emojis. |
| `UTF_16LE`/`UTF_16BE` | Encodes UTF-16 code units with explicit byte order. | Wrong endianness or BOM protocol yields corrupted text. |

**Byte exactness cannot be concluded solely from** `String.equals`. If code decoded invalid bytes using a replacement-character policy, comparing strings still fails to recover or verify the original bytes.

## 6. "Text Round-Trip" Has Two Directions to Test Separately

### Direction A: String → encode → decode → String

For a valid Java string that the charset can fully represent without transformation steps, we expect:

```text
originalText == decode(encode(originalText, charset), charset)
```

With UTF-8 and valid Unicode data, this normally preserves the string exactly. However, a Java string can contain **unpaired surrogates**, which are not valid Unicode scalar values; if an encoder uses a replacement policy, the round-trip **can lose information**. Choose report-on-error mode when the format requires strict encoding.

### Direction B: raw bytes → decode → encode → raw bytes

This direction is stronger:

```text
originalBytes == encode(decode(originalBytes, charset), charset)
```

It holds only when the byte sequence is valid and decoding/re-encoding under the protocol yields a unique canonical byte representation. With invalid UTF-8, broken encodings, charsets with multiple encodings, replacement policies, or canonicalization, there is no guarantee raw bytes are reproduced.

**Test both directions when you genuinely need both.** For binary files with no text decoding requirement, compare bytes only. For documents normalized by policy, test logical equivalence rather than demanding raw byte exactness.

## 7. Standalone Java 17+ Example: File Bytes, UTF-8 Round-Trip, and Pitfalls

This program creates temporary files and writes text containing Vietnamese characters, an emoji, and a newline. It copies the file, verifies bytes via `Arrays.equals` and `Files.mismatch`, then reads the text and re-encodes it. The example also checks the UTF-8 bytes of `é`, compares Unicode normalization, line endings, and rejection of malformed UTF-8.

Save as **`ByteExactRoundTripDemo.java`**:

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

1. `text` contains Vietnamese characters and an outside-BMP emoji; `text.getBytes(UTF_8)` produces bytes using an explicit encoding.
2. `Files.write(source, expected)` writes the original bytes; `Files.copy` copies to another temporary file. `Arrays.equals` compares the byte arrays; `Files.mismatch == -1` confirms both files have identical byte contents.
3. `Files.readString(copy, UTF_8)` reads the text. `String.equals` checks the UTF-16 code unit sequence; re-encoding verifies the same bytes in this valid UTF-8 case.
4. `"é"` in UTF-8 is `C3 A9`; `HexFormat` outputs `c3a9`.
5. `"café"` uses the precomposed `é` character, while `"cafe\u0301"` uses `e` + combining acute accent. Their bytes differ, yet after `Normalizer.normalize(..., NFC)` they compare equal.
6. `"A\nB"` and `"A\r\nB"` have different bytes: `0A` versus `0D 0A`. Editors may display both files identically, so visual text rendering cannot prove byte equality.
7. The byte sequence `C3 28` is not valid UTF-8. `CharsetDecoder` with `CodingErrorAction.REPORT` throws an error so tests catch it instead of silently substituting `U+FFFD`.
8. `finally` cleans up both temporary files. The demo uses small data; for very large files, avoid `Files.readAllBytes` to bound memory usage.

**Key takeaway:** the example proves **three independent claims**: intact byte copying, correct text round-tripping with the right charset, and strict decoder rejection of invalid input. Never use one claim's result as a substitute assertion for another.

## 8. Checking Bytes After `FileChannel` or Streams with Partial I/O

With `InputStream.read(buffer)`, the return value is the number of bytes **actually read** or `-1` at EOF. Never assume a single `read` fills the array, especially when reading from sockets, pipes, or large data.

When copying in chunks, follow this rule:

```java
// Snippet: in and out are already-opened InputStream/OutputStream.
byte[] buf = new byte[8192];
for (int n; (n = in.read(buf)) != -1; ) {
    out.write(buf, 0, n);
}
```

This is a snippet; `IOException` handling and `try-with-resources` are the caller's responsibility. With a typical `InputStream`, `read(byte[])` can return fewer bytes than `buf.length`; calling `out.write(buf)` instead of `out.write(buf,0,n)` will write stale bytes from the end of the array.

With `FileChannel` and `ByteBuffer`:

```java
// Snippet: source and target are FileChannels,
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

This is a fail-fast pattern for blocking file channels in an application-controlled context; **do not** copy the `n==0` policy verbatim to non-blocking `SocketChannel`, where you must wait for readiness rather than throwing an error. Post-copy verification using `Files.mismatch` or a trusted digest is much more meaningful than merely checking the number of bytes passed to `write`.

If code uses `ByteBuffer.array()`, remember that the backing array may be larger than the valid data region, and the buffer may be direct, read-only, or sliced and not support `array()`. Use `position`/`limit`/`remaining` or an appropriately bounded view rather than assuming the entire array is payload.

## 9. Characters, Code Points, UTF-16 Code Units, and Byte Counts

A Java `String` is a sequence of **UTF-16 code units**. Consequently:

- `String.length()` returns the number of code units, not Unicode code points and not UTF-8 bytes.
- A supplementary character, such as `😀`, takes **two UTF-16 code units** and typically **four UTF-8 bytes**.
- A precomposed `é` character typically takes one code unit and two UTF-8 bytes.
- Combining characters can form a single glyph from multiple code points/code units; the number of visible glyphs does not equal `String.length()`.

Illustrative example:

```java
String emoji = "😀";
System.out.println(emoji.length()); // 2 UTF-16 code units
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
System.out.println(emoji.getBytes(StandardCharsets.UTF_8).length); // 4
```

This is a snippet. If a protocol requires a header specifying payload length **in bytes**, use `data.length` of the encoded byte array, not `str.length()`. In a binary protocol, an incorrect byte count truncates the payload or reads into the next frame.

To iterate Unicode code points, consider `String.codePoints()`, though even the code point count does not equal the number of user-perceived grapheme clusters. For byte-exactness comparisons, the proper unit remains the **byte sequence**.

## 10. Unicode Normalization: "Looks the Same" Does Not Mean `String.equals`

Example representations of an accented character:

```text
NFC / composed: "é"           U+00E9        UTF-8 C3 A9
NFD / decomposed: "e◌́"        U+0065 U+0301 UTF-8 65 CC 81
```

Two strings can render identically in the UI yet have different bytes, and Java `String.equals` will typically return `false` because their UTF-16 code units differ. If business rules treat them as equivalent under Unicode canonical equivalence, define an explicit **normalization rule**:

```java
String left = Normalizer.normalize(sourceText, Normalizer.Form.NFC);
String right = Normalizer.normalize(restoredText, Normalizer.Form.NFC);
boolean sameMeaningByPolicy = left.equals(right);
```

This is a snippet importing `java.text.Normalizer` with application-provided string variables. Use **NFC** when the product requires canonical normalization, though normalization is not always harmless: when checking raw files, digital signatures, protocol bytes, file paths, or data requiring byte-exactness, normalization alters bytes and **must not be performed automatically**.

The forms `NFC`, `NFD`, `NFKC`, and `NFKD` serve different purposes; compatibility normalization such as `NFKC` can transform certain compatibility characters into different visual forms or meanings. Choose according to the contract rather than applying it blindly to "fix encoding bugs."

## 11. Line Endings and APIs That Lose Line Boundaries

Three common line-ending formats:

| Form | Hex | Usage |
| --- | --- | --- |
| LF | `0A` | Common in Unix/Linux environments and many protocols. |
| CRLF | `0D 0A` | Common on Windows and several network protocols. |
| CR | `0D` | Exists in legacy data or certain specialized formats. |

`BufferedReader.readLine()` returns line contents **without the line terminator**. Therefore, reading lines with `readLine()` and writing them back with `writer.newLine()` can alter the original file's bytes:

- A file with `\n` gets written with `\r\n` on another machine.
- Whether the file ended with a trailing newline or not can be lost.
- Mixed newline styles within the same file are not preserved.
- Individual CR/LF boundaries may be interpreted per the reader's policy.

Likewise, line-oriented APIs such as `Files.readAllLines` and `Files.lines` are suitable for processing **per-line content**, not for verifying byte-for-byte preservation of line breaks.

When you need to preserve the file intact, operate on bytes or preserve exact line separators. When business rules call for normalizing line endings, write a dedicated test proving **the normalized output** and document it as an intentional transformation rather than a raw byte round-trip.

## 12. BOM and Invisible Leading Bytes

Some text files begin with a **Byte Order Mark (BOM)**. For example, the UTF-8 BOM consists of three bytes:

```text
EF BB BF
```

UTF-8 does not need a BOM to indicate byte order; nevertheless, some software writes UTF-8 files with a BOM. Two files with identical visible text where one has a BOM and the other does not **will differ in SHA-256, size, and byte exactness**.

Questions to settle explicitly:

1. Does the protocol allow a BOM?
2. Does the parser detect/strip the BOM, or treat it as a `U+FEFF` code point?
3. Does the writer always prepend a BOM, never prepend one, or copy it as-is?
4. Which endianness does UTF-16 use; is there a BOM, or are `UTF_16LE`/`UTF_16BE` specified explicitly?

When byte exactness is required, **the BOM is data to be checked like any other byte**. When semantic text round-tripping is required, both sides must agree on the BOM rule before comparing strings. Never silently add or strip a BOM just because an OS editor behaves differently.

## 13. Strict Decoding and Invalid-Data Errors

Some convenience APIs handle malformed input with **replacement characters**, causing silent data loss. When a format requires valid UTF-8, use a decoder configured with `CodingErrorAction.REPORT`:

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

**Malformed** generally refers to a byte sequence violating the encoding structure; **unmappable** refers to data with no valid character representation in the target charset. In UTF-8, an example of malformed input is `C3 28`: byte `C3` expects a valid continuation byte, but the next byte is `28`.

Similarly, when encoding text into a charset with fewer characters:

```java
CharsetEncoder strictAscii = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
try {
    ByteBuffer encoded = strictAscii.encode(CharBuffer.wrap("Tiếng Việt"));
} catch (CharacterCodingException unsupported) {
    // Data contains characters that cannot be represented in ASCII.
}
```

This is a snippet. `String.getBytes(Charset)` may substitute replacement bytes for unmappable characters or malformed sequences per the API, so to **detect invalid data** instead of silently replacing it, use a strict `CharsetEncoder` as shown above. Avoid accidental "passing tests" caused by both writer and reader using lossy replacement policies.

## 14. Golden Fixtures and Mandatory Test Cases

Good tests do not merely round-trip the same encode/decode functions; if both share a symmetric bug, they can validate each other falsely. You need **golden bytes independent** of the code under test.

Recommended fixture suite:

| Fixture | Characteristic Bytes or Content | What Defect It Catches |
| --- | --- | --- |
| Empty file | Zero bytes. | Unexpected BOM, newline, or header insertion. |
| Short ASCII | `abc` = `61 62 63` | Basic payload and content length. |
| Null byte | `00` inside payload. | Treating null as a C-style string terminator. |
| High bytes | `80 FF` | Signed byte handling, accidental text decoding. |
| UTF-8 Vietnamese accents | `đ, ế, ộ` | Wrong charset / replacement characters. |
| Supplementary emoji | `😀` | Surrogate pairs and byte counts. |
| NFC vs. NFD | `C3 A9` vs. `65 CC 81` | Visual equality does not imply byte equality. |
| LF and CRLF | `0A` vs. `0D 0A` | Line-ending rewriting. |
| With/without BOM | `EF BB BF` before text | BOM policy mismatches. |
| Malformed UTF-8 | `C3 28` or truncated multibyte | Strict decoder must reject. |
| Unpaired UTF-16 surrogate | E.g., a high surrogate without a low surrogate | Strict encoder must reject. |
| Multi-chunk | Data longer than buffer, short final chunk | Partial reads and stale bytes. |
| Real binary file | Small verified PNG/ZIP fixture | Avoiding `String` as an intermediate representation. |
| Large file | Multiple MiB/GB per test infrastructure | Streaming, memory bounds, timeouts, safeguards. |

For hex-defined fixtures, construct expected bytes using `HexFormat.parseHex` from a reviewed string or protocol specification. Avoid generating expected bytes using the very encode API under test and then claiming you tested encoding correctness.

## 15. JUnit 5 Example: Exact Assertions (JUnit-Dependent Snippet)

In a project with JUnit Jupiter installed, you can write:

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

This is another test snippet; do not print sensitive payloads in failure messages. JUnit `assertArrayEquals` is usually convenient for array equality, while `mismatch` helps when you want to report the exact offset.

For large files, avoid embedding the entire file in assertion messages. Separate integration tests comparing with `Files.mismatch`, logging sizes, the first mismatching offset, and bounded context.

## 16. Round-Tripping with `Reader`/`Writer` and `CharsetDecoder`

If the application genuinely reads and writes **text**, `Reader`/`Writer` APIs are appropriate because they operate on characters rather than bytes. However, tests must account for the fact that reading text and writing it back **re-encodes the data**:

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

This is a snippet requiring imports for `BufferedReader`, `BufferedWriter`, `Files`, `StandardCharsets`, and `IOException` handling. Note the difference between copying **char arrays** versus **lines**: continuously reading/writing `char`s preserves decoded newline characters, whereas `readLine`/`newLine` can alter them.

Even then, using `Reader`/`Writer` **does not** automatically guarantee byte exactness: decoders/encoders may handle BOMs, malformed input, replacements, charsets, or canonicalization differently. If raw original bytes must remain untouched, copy at the byte layer first and verify with file mismatch.

For long encoded streams, low-level `CharsetDecoder.decode(ByteBuffer, CharBuffer, boolean)` maintains incremental state to handle characters split across two chunks; never call `new String(chunk, UTF_8)` independently on each byte chunk received from a socket because a multibyte character may be split across chunks.

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

that **does not** decode the complete `C3 A9` sequence properly. Each isolated chunk is invalid on its own, and convenience decoders may produce replacement characters.

The right approaches:

- For small payloads, **accumulate bytes** until the entire message arrives, then decode once.
- For large streams, use `InputStreamReader`/`BufferedReader` reading continuously from the stream so the decoder preserves state across internal buffer boundaries.
- Or manage incremental `CharsetDecoder` with `CoderResult`, the `endOfInput` flag, `flush()`, and buffer `compact()` when incomplete UTF-8 bytes remain.

If a protocol parser frames messages by **byte length**, first verify all bytes of the frame have arrived before decoding; never add `String.length()` as a byte count in a header.

## 18. Handling Large Files Without Unbounded RAM Usage

Convenience APIs like `Files.readAllBytes` and `Files.readString` are great for **unit tests with small fixtures**. For large files, loading all bytes or text into RAM can exhaust the heap, trigger long GC pauses, or prevent tests from reflecting production streaming behavior.

Several strategies:

1. **File-to-file exact check:** use `Files.mismatch(pathA, pathB)` to get the first mismatching offset.
2. **Streaming compare:** open two input streams; read in chunks, compare active slice contents on each read, and handle differing sizes and partial reads.
3. **Streaming hash:** when checking against a trusted reference digest, compute SHA-256 via `MessageDigest`/`DigestInputStream` without retaining all bytes.
4. **Small golden fixtures:** for protocol serializers, pick test vectors covering boundary cases rather than multi-gigabyte files.
5. **Boundary tests:** sizes `0`, `1`, `bufferSize-1`, `bufferSize`, `bufferSize+1`, multiples of `bufferSize+1`; especially test a short final chunk.
6. **Resource closure:** use `try-with-resources` for streams/channels and handle closing errors.
7. **Concurrency:** if the source is being modified by another process, comparison or hashing may not observe a consistent snapshot. Isolate an immutable source, take a snapshot, or coordinate with the writer before checking.

Do not use `MessageDigest.isEqual` to "replace file content comparison" when both digests are computed from files that can change concurrently and the application requires a specific version. Digest comparison works when the target is read stably and the trust/reference criteria are clearly defined.

## 19. Common Errors and Their Causes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Test passes yet file has trailing extra bytes | String comparison after trim, or prefix-only comparison. | Compare byte length and all bytes with `Arrays.equals`/`Files.mismatch`. |
| Text looks identical in editor yet mismatches | Differs in BOM, line endings, Unicode normalization, or invisible whitespace. | Print hex/offset, verify raw bytes first. |
| Emoji breaks byte length | Using `String.length()` as UTF-8 byte count. | Encode and use `byte[].length`. |
| Only the final chunk is corrupted | Writing the entire buffer instead of the `n` bytes read. | Use `write(buffer,0,n)` or proper `ByteBuffer.limit`. |
| Byte `FF` prints as `-1` | Java `byte` is signed. | Use `Byte.toUnsignedInt` and hex. |
| Wrong charset only on another machine | Relying on default charset instead of specifying it explicitly. | Use `StandardCharsets.UTF_8` consistently. |
| Decoding invalid text passes tests | Decoder silently replaces invalid input. | Use `CharsetDecoder` with `CodingErrorAction.REPORT`. |
| ASCII encoding "succeeds" with Vietnamese text | Encoder replaces unmappable characters. | Use strict `CharsetEncoder` and assert the error. |
| Text changes from `LF → CRLF` | `BufferedReader.readLine` followed by `newLine()`. | Copy bytes or preserve line endings per policy. |
| Data corrupted when decoding stream in chunks | Multibyte UTF-8 split across two reads. | Use stateful streaming decoder or proper accumulation. |
| Hash matches yet file is the wrong version | Reference hash is not bound to identity/version. | Use a trusted manifest including algorithm, path, version, and digest. |
| Copying through text APIs corrupts ZIP | Attempting to decode binary bytes as `String`. | Use `InputStream`/`OutputStream` or `FileChannel`. |
| Flaky/non-reproducible tests on CI | Depends on locale, timezone, EOL, default charset, or path separator. | Use deterministic fixtures and explicit configuration. |
| Concurrent writer causes test flakiness | Comparing without a snapshot while file changes mid-read. | Ensure file immutability or copy/snapshot before checking. |
| Printing full hex dumps to logs for debugging | Exposes sensitive data or bloats logs. | Log only offsets and bounded context when permitted. |

## 20. Designing a Reliable Test Suite

A strong suite spans multiple layers:

**Encoder/decoder unit tests:** verify against independent golden bytes; test valid and invalid UTF-8; assert errors on unpaired surrogates or malformed byte sequences; test explicit charsets without relying on defaults.

**Read/write helper tests:** use bytes with `00`, `FF`, deterministic seeded random data, and sizes spanning buffer boundaries; verify exact bytes after a copy pass.

**Text round-trip tests:** test Vietnamese text, emojis, combining marks, line breaks, trailing empty lines, and BOM policies; decide explicitly whether the test checks exact `String.equals` or normalized equivalence.

**Integration tests:** write files, close resources, reopen from disk, check `Files.mismatch`, and test behavior on Windows/Linux when needed; document assumptions that differ across OSes.

**Regression tests:** every discovered encoding or copy bug should get a fixture capturing the exact failing bytes. Never "fix" expected output just to make a test pass without confirming the real data contract.

**Negative tests:** truncated data, invalid UTF-8, unreadable files, disk-full/permission errors where the test environment supports them, corrupted frames, duplicate bytes, and source modification during read; outcomes must fail clearly rather than returning false success.

Especially for serializers/protocols, avoid relying solely on self-confirming tests like:

```text
actualBytes = encode(input)
restored = decode(actualBytes)
assertEquals(input, restored)
```

If `encode` and `decode` share a symmetric bug, this test still passes. Add canonical **golden byte vectors** and independent tests for both encoding and decoding.

## 21. Practice Exercises

**Exercise 1 — Golden UTF-8.** Use `HexFormat.parseHex("61c3a90a")` as expected bytes for `"aé\n"`. Write a JUnit test performing exact comparison with `assertArrayEquals`, and explain why an independent hex fixture is required instead of generating expected bytes with the logic under test.

**Exercise 2 — Single Corrupted Byte.** Create a 1,024-byte `byte[]`, modify the byte at index 511, and use `Arrays.mismatch` to confirm the mismatch position. Also test arrays of different lengths sharing a common prefix.

**Exercise 3 — BOM.** Create two UTF-8 files containing `abc`, one prefixed with `EF BB BF`. Use `Files.mismatch`, `Files.size`, and hex output to report the difference. Explicitly define whether a "raw exact" test and a "semantic text" test accept the BOM.

**Exercise 4 — Line Endings.** Write fixtures with CRLF, LF, and one mixing both. Copy using streams (without `readLine`) and compare exact bytes; then intentionally normalize newlines and verify output under the new policy.

**Exercise 5 — NFC/NFD.** Compare `"café"` and `"cafe\u0301"` using `equals`, UTF-8 byte arrays, and `Normalizer.Form.NFC`. Explain why the conclusions differ and when normalization is forbidden.

**Exercise 6 — Invalid UTF-8.** Use the byte array `C3 28`. Compare strict decoder behavior with convenience APIs that apply replacement. Ensure a pipeline requiring exact data throws an error rather than silently altering bytes.

**Exercise 7 — Split Multibyte.** Feed bytes `C3 A9` across two read chunks `C3` and `A9`. Compare decoding each chunk separately with decoding the full stream. Fix it using `InputStreamReader` or incremental `CharsetDecoder`.

**Exercise 8 — Large File.** Generate a seeded data file many times larger than the buffer, then copy via `FileChannel`; assert `Files.mismatch == -1`. Inject an intentional single-byte error in the middle of the file and print the mismatch offset without logging the whole content.

**Exercise 9 — Text Length vs. Payload Length.** Build a protocol sending `"Việt 😀"` as UTF-8 with a 4-byte length header; verify you use `encoded.length`, not `String.length()`. Simulate a receiver reading the payload across multiple chunks.

**Exercise 10 — Regression Fixture.** Pick a real bug such as an inserted BOM or LF converted to CRLF. Save before/after fixtures in hex alongside the expected mismatch offset; write a test so the bug never returns.

### Self-Check Questions

1. Can `String.equals` prove byte-for-byte equality?
2. What value does `Files.mismatch` return when two files are completely identical?
3. When a source stream reads 7 bytes into an 8,192-byte array, how many bytes should be written?
4. Why can calling `getBytes()` without a charset make tests unstable across environments?
5. What is `String.length()` for a supplementary emoji, and how many UTF-8 bytes does it use?
6. When can two strings display identically yet have `Arrays.equals(utf8A, utf8B) == false`?
7. How does `readLine`/`newLine` affect raw line-ending bytes?
8. Why is a strict decoder necessary for text data that must preserve integrity?
9. Why should you not decode partial UTF-8 bytes independently for each chunk?
10. Is a passing encode→decode test enough to prove an encoder complies with a golden wire format?

## 22. References

- [Java SE 21 — Arrays](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html): `equals` and `mismatch` for primitive arrays.
- [Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): `readAllBytes`, `readString`, `write`, `copy`, `mismatch`.
- [Java SE 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): standard built-in charsets.
- [Java SE 21 — CharsetDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html): detecting malformed/unmappable input.
- [Java SE 21 — CharsetEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html): error handling when encoding Strings to bytes.
- [Java SE 21 — HexFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HexFormat.html): formatting and parsing bytes as hex.
- [Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html): Unicode normalization NFC/NFD/NFKC/NFKD.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): position/limit/remaining and NIO operations.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): assertions and data-driven tests.

**Remember:** For **byte-exact** requirements, verify every actual byte using `Arrays.equals`/`Arrays.mismatch`/`Files.mismatch` and report the offset on failure. For **text round-trips**, specify the charset explicitly, test both encoding/decoding and golden bytes, and control BOM, newlines, Unicode normalization, and malformed input errors. "Looks right on screen" and "no exception thrown" are no substitute for proving data preservation.
