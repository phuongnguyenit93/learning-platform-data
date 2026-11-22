# Unicode Data, BOM, and Characters Split Across Chunks in Java I/O

## 1. The Problem to Solve

When a Java application reads or writes text, it does not actually transfer "characters" directly over disk or a socket. It transfers **bytes**. Those bytes must be encoded or decoded according to a specific **charset**, such as UTF-8 or UTF-16.

A program may handle ASCII text fine yet corrupt Vietnamese text, emoji, or people's names when it:

- Splits a file/network stream into **byte chunks** and calls `new String(chunk, UTF_8)` on **each chunk individually**.
- Reads the bytes of a multi-byte UTF-8 character across separate read calls.
- Confuses **bytes**, **UTF-16 code units**, **Unicode code points**, and **user-visible characters**.
- Fails to recognize a **BOM** (Byte Order Mark) at the beginning of a file.
- Decodes UTF-16 with the wrong byte order.
- Replaces malformed bytes with `�` without detecting that the source data was corrupted.
- Confuses the byte count in network framing with `String.length()`.
- Cuts a buffer at an arbitrary position and treats that as a character boundary.

This lesson sits in the **Testing and Diagnostics** group of Java Core I/O: beyond decoding properly, we will build boundary test cases, print byte hex dumps, verify error policies, handle BOMs, and check Unicode normalization.

**Core principle:** The boundary of a single `InputStream.read(...)`, `FileChannel.read(...)`, or network packet **is not** a Unicode character boundary. Decoding must maintain **continuous state** across incoming byte reads.

## 2. Unicode Is Not Synonymous with UTF-8

### Unicode code point

Unicode defines **code points**, typically written as `U+XXXX`. For example:

| Content | Unicode code point | UTF-8 | UTF-16 |
|---|---|---|---|
| `A` | `U+0041` | `41` | `0041` |
| `é` | `U+00E9` | `C3 A9` | `00E9` |
| `☕` | `U+2615` | `E2 98 95` | `2615` |
| `😀` | `U+1F600` | `F0 9F 98 80` | `D83D DE00` (surrogate pair) |

The UTF-16 sequences in the table are **code unit values**; their actual bytes also depend on big-endian/little-endian byte order.

### UTF-8 is a variable-length encoding

In UTF-8, a valid Unicode code point can occupy **1 to 4 bytes**. Bytes belonging to the same code point **can land in two different read chunks**.

Example with `☕`:

```text
Unicode code point: U+2615

UTF-8 bytes: E2 98 95
             ^^ ^^ ^^
             1  2  3

Chunk #1: E2 98
Chunk #2: 95

Neither chunk alone is sufficient to decode U+2615.
```

If a developer calls `new String(chunk1, UTF_8)` and `new String(chunk2, UTF_8)` and concatenates the two strings, each decode treats that chunk's bytes as a standalone malformed sequence, producing the replacement character `U+FFFD`.

### UTF-16 is a 16-bit code unit encoding

In Java, `String` uses a sequence of **UTF-16 code units** to represent content (the `char` API corresponds to one code unit). A supplementary-plane code point, such as `😀`, requires **two code units**:

```text
U+1F600 -> high surrogate D83D + low surrogate DE00

Java "😀".length() == 2
"😀".codePointCount(0, "😀".length()) == 1
```

In a UTF-16 file, each code unit consists of two bytes; reading it properly requires knowing **endianness**, as well as handling surrogate pairs. A file can also be split right **between the two bytes of one code unit**, or **between the two surrogates**.

## 3. Four Commonly Confused Counting Units

Consider the string:

```java
String text = "A☕B😀C";
```

The different quantities:

| Quantity | Value | Explanation |
|---|---:|---|
| `text.getBytes(UTF_8).length` | 10 | 1 + 3 + 1 + 4 + 1 UTF-8 bytes |
| `text.length()` | 6 | Number of UTF-16 code units; emoji takes 2 |
| `text.codePointCount(0,text.length())` | 5 | Number of Unicode code points |
| User-visible grapheme clusters | 5 in this example | Not always equal to code points |

**Never use `String.length()` as the byte size to send**, never slice a byte stream by character count, and never assume one Java `char` is always a complete Unicode character.

Example of accented character composition:

```text
"é"        U+00E9            (one code point)
"e\u0301"  U+0065 U+0301     (two code points)

Two strings can look almost identical yet have different representations.
```

These two representations can have different UTF-8 byte counts, `String.equals` is not necessarily true, and normalization may be considered depending on business rules.

For complex emoji with zero-width joiners, variation selectors, or combining marks, "one visible character" can consist of **many** code points. Do not assume `codePointCount` always equals the number of grapheme clusters.

## 4. A Single `read()` Does Not Guarantee a Full Character

I/O APIs typically return the number of bytes actually received:

```java
int n = inputStream.read(buffer);
```

A single read can return **fewer bytes than the buffer length**, even when the source has more data, depending on stream type and timing. With network sockets, one peer send does not correspond to one application read.

Example file containing UTF-8 bytes:

```text
41 E2 98 95 42 F0 9F 98 80 43
 A    ☕      B       😀        C
```

The reader fetches 2-byte chunks:

```text
Chunk 1: 41 E2
Chunk 2: 98 95
Chunk 3: 42 F0
Chunk 4: 9F 98
Chunk 5: 80 43
```

No I/O event declares "this is one Unicode character". Chunk boundaries are determined purely by buffers, providers, and data arrival timing.

### Anti-pattern: decoding each chunk separately

```java
byte[] buffer = new byte[2];
StringBuilder text = new StringBuilder();

int n;
while ((n = input.read(buffer)) != -1) {
    text.append(new String(buffer, 0, n, StandardCharsets.UTF_8));
}
```

This is **broken Unicode demo code**, assuming `input` is an `InputStream`. Each `new String` call creates an **independent decoding session**, forgetting that the trailing byte `E2` of the previous chunk still needed `98 95` in the next chunk.

Choosing a larger buffer **reduces the probability** of splitting a character in some tests, but **does not solve the problem completely**. Any finite buffer can end mid-character.

## 5. Simplest Approach: Use a `Reader` with an Explicit Charset

If the goal is **reading text** without managing raw byte framing manually, use `InputStreamReader` or `Files.newBufferedReader` with the proper charset:

```java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {

    String line;
    while ((line = reader.readLine()) != null) {
        // Process each complete Unicode line assembled by the decoder.
    }
}
```

This is an illustrative snippet requiring `BufferedReader`, `Files`, `Path`, and `StandardCharsets`; `path` must be declared.

`InputStreamReader` retains **decoder state across character reads**. If a UTF-8 code point is split across multiple underlying byte reads, the reader holds the incomplete bytes and waits for the next byte instead of decoding each byte chunk as a standalone sequence.

### Specify the charset explicitly

```java
try (Reader reader = new InputStreamReader(
        Files.newInputStream(path), StandardCharsets.UTF_8)) {
    char[] chars = new char[256];
    int n;
    while ((n = reader.read(chars)) != -1) {
        // Use exactly n UTF-16 code units.
    }
}
```

A `Reader` returns **UTF-16 code units** into `char[]`, not "exactly `n` code points". Even when the UTF-8 decoder handles multi-byte splits properly, **a surrogate pair in `char[]` can still be split across character reads** if the buffer/chunk runs out or a read stops right on that boundary.

If the task only displays or writes text back out, you can keep passing characters through reader/writer. If you need to count code points, tokenize/segment graphemes, or validate surrogates, use appropriate Unicode APIs rather than treating every `char` element independently.

## 6. `CharsetDecoder`: Continuous Decoding with `ByteBuffer`

When an application handles a **binary protocol**, `ByteBuffer`, or receives a stream in arbitrary segments, `java.nio.charset.CharsetDecoder` gives full control over the decoding process.

Components:

- `CharsetDecoder`: maintains decoding state across calls.
- Input `ByteBuffer`: holds newly received bytes **plus leftover bytes from an incomplete character in the previous round**.
- Output `CharBuffer`: receives decoded UTF-16 code units.
- `CoderResult.UNDERFLOW`: the decoder consumed what it could from the current input; incomplete bytes may remain to be kept.
- `CoderResult.OVERFLOW`: the output buffer ran out of space; drain `CharBuffer` and continue decoding.
- `CoderResult.isError()`: malformed or unmappable bytes per the charset/error policy.
- `decoder.decode(input, output, endOfInput)`: pass `true` only once the byte stream has genuinely ended.
- `decoder.flush(output)`: flushes final state **after `decode(..., true)` has returned `UNDERFLOW`**.

### Standard buffer cycle

```text
ByteBuffer in WRITE MODE
     |   (may retain trailing bytes from previous round)
     +-- append new bytes
     |
     v
input.flip()  -> READ MODE
     |
     v
decoder.decode(input, chars, eof)
     |
     +-- OVERFLOW -> chars.flip(), drain, chars.clear(), continue decode
     |
     +-- ERROR -> throwException / error policy
     |
     +-- UNDERFLOW -> keep unconsumed bytes
     |
input.compact() -> shift incomplete bytes to front, back to WRITE MODE
     |
     +-- if not EOF: read more bytes into remaining space, loop
     |
     +-- if EOF: decoder.flush(chars) until UNDERFLOW
```

`ByteBuffer.compact()` is the key mechanism. It **does not discard the remainder**: it copies the unconsumed bytes in `[position, limit)` to the start of the buffer and sets `position` right after those remaining bytes. The next read simply appends new bytes behind them.

Do not call `input.clear()` after every `UNDERFLOW`: `clear()` allows overwriting the entire input buffer and **loses the waiting bytes**.

## 7. Complete Java 17+ Example: Reading UTF-8 in 2-Byte Chunks

The program below:

1. Creates a temporary file containing `A☕B😀C` encoded in UTF-8.
2. Reads **at most 2 bytes** per call, deliberately splitting mid-representation of `☕` and `😀`.
3. Reuses one `CharsetDecoder` throughout, preserving leftover bytes with `compact()`.
4. Verifies the round-trip and compares byte count, UTF-16 code units, and code points.
5. Rewrites the file with a leading **UTF-8 BOM** to demonstrate that a normal decoder sees `U+FEFF` as a character and how to apply a BOM policy.
6. Closes/cleans up the temporary file.

Save as **`UnicodeBoundaryDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class UnicodeBoundaryDemo {

    public static void main(String[] args) throws IOException {
        String original = "A☕B😀C";
        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
        Path file = Files.createTempFile("unicode-chunk-", ".txt");

        try {
            Files.write(file, utf8);
            String restored = decodeUtf8InTwoByteChunks(file, false);

            System.out.println("UTF-8 bytes: " + utf8.length);
            System.out.println("UTF-16 units: " + original.length());
            System.out.println("Code points: " +
                    original.codePointCount(0, original.length()));
            System.out.println("Split-safe equals: " +
                    original.equals(restored));

            byte[] withBom = new byte[utf8.length + 3];
            withBom[0] = (byte) 0xEF;
            withBom[1] = (byte) 0xBB;
            withBom[2] = (byte) 0xBF;
            System.arraycopy(utf8, 0, withBom, 3, utf8.length);
            Files.write(file, withBom);

            String rawWithBom =
                    decodeUtf8InTwoByteChunks(file, false);
            String clean =
                    decodeUtf8InTwoByteChunks(file, true);

            System.out.println("Leading BOM character: " +
                    rawWithBom.startsWith("\uFEFF"));
            System.out.println("After BOM policy: " + clean);
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static String decodeUtf8InTwoByteChunks(
            Path file, boolean stripLeadingBom) throws IOException {

        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        ByteBuffer inputBytes = ByteBuffer.allocate(8);
        CharBuffer outputChars = CharBuffer.allocate(4);
        StringBuilder result = new StringBuilder();

        try (InputStream stream = Files.newInputStream(file)) {
            boolean endOfInput = false;

            while (!endOfInput) {
                int bytesToRead = Math.min(2, inputBytes.remaining());
                if (bytesToRead == 0) {
                    throw new IOException("Input buffer made no progress");
                }

                int n = stream.read(
                        inputBytes.array(),
                        inputBytes.position(),
                        bytesToRead);

                if (n == -1) {
                    endOfInput = true;
                } else if (n == 0) {
                    throw new IOException("Input stream made no progress");
                } else {
                    inputBytes.position(inputBytes.position() + n);
                }

                inputBytes.flip();

                while (true) {
                    CoderResult step = decoder.decode(
                            inputBytes, outputChars, endOfInput);

                    outputChars.flip();
                    result.append(outputChars);
                    outputChars.clear();

                    if (step.isError()) {
                        step.throwException();
                    }
                    if (step.isUnderflow()) {
                        break;
                    }
                    // OVERFLOW: outputChars was drained, continue decoding.
                }

                inputBytes.compact();
            }

            while (true) {
                CoderResult step = decoder.flush(outputChars);

                outputChars.flip();
                result.append(outputChars);
                outputChars.clear();

                if (step.isError()) {
                    step.throwException();
                }
                if (step.isUnderflow()) {
                    break;
                }
                // OVERFLOW: more characters in decoder, keep draining.
            }
        }

        String text = result.toString();
        if (stripLeadingBom && text.startsWith("\uFEFF")) {
            return text.substring(1);
        }
        return text;
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac UnicodeBoundaryDemo.java
java UnicodeBoundaryDemo
```

**Expected exact stdout when temporary file I/O succeeds:**

```text
UTF-8 bytes: 10
UTF-16 units: 6
Code points: 5
Split-safe equals: true
Leading BOM character: true
After BOM policy: A☕B😀C
```

Why is this example correct?

- `inputBytes` in write mode receives at most 2 bytes per turn. Upon encountering the first 2 bytes of `☕`, the decoder returns `UNDERFLOW` and does not treat them as malformed because EOF has not been reached.
- `inputBytes.compact()` keeps the undecoded bytes. The next turn appends the third byte, completing the sequence `E2 98 95`.
- The same applies to `😀` with 4 UTF-8 bytes. The decoder retains leading bytes across multiple turns until all bytes arrive.
- `outputChars` holds the UTF-16 result. `StringBuilder.append(CharBuffer)` appends the decoded code units.
- `CodingErrorAction.REPORT` causes genuinely invalid bytes or a truncated trailing sequence to throw an error instead of silently inserting `�`.
- `endOfInput=true` is set **only when `read` returns `-1`**. Passing `true` early while a chunk holds partial bytes causes the decoder to report leftover bytes as malformed.
- After the final decode, `decoder.flush` completes decoder state per protocol.
- `rawWithBom` starts with `U+FEFF` decoded from bytes `EF BB BF`. The example's policy strips **only the leading `U+FEFF` character**; it does not delete similar characters occurring mid-content.

**Intentional limitations:** The example uses small buffers, a small file, and a `StringBuilder` to make the mechanics clear. In production with very large files or untrusted sources, enforce output limits, manage rate/timeouts, and process decoded characters incrementally rather than accumulating everything in one `StringBuilder`.

## 8. Deep Dive into `CharsetDecoder` States

### UNDERFLOW

An `UNDERFLOW` result generally means the decoder **cannot make further progress** with the provided input. In streaming mode, `ByteBuffer` may still hold 1–3 leading bytes of an incomplete UTF-8 sequence. Keep them using `compact()`.

Example:

```text
Input bytes: E2 98
Decoder: UNDERFLOW
input.remaining(): 2 (unconsumed)
compact(): keeps E2 98
append next: 95
decode again: -> ☕
```

When `endOfInput=true`, incomplete bytes at EOF can no longer wait: they must be handled according to the malformed-input policy.

### OVERFLOW

`OVERFLOW` does not mean the file is too large or bytes are invalid. It means **`CharBuffer` lacks space for the next UTF-16 code units**. Resolve it with:

```java
outputChars.flip();
process(outputChars);
outputChars.clear();
```

This is an illustrative snippet, with `process` defined by the application. After draining, call `decode` again **on the input at its current position**—do not discard remaining input or create a new decoder.

### ERROR

`CoderResult.isError()` covers malformed-input or unmappable-character errors per charset and policy:

- `REPORT`: returns an error result; `throwException()` throws an appropriate checked exception such as `MalformedInputException`.
- `REPLACE`: substitutes the decoder's replacement string/character and continues.
- `IGNORE`: drops the invalid input, risking silent data loss without a trace.

`REPORT` is typically best when testing data pipelines, reading configuration files, decoding schema-driven protocols, or handling content requiring exact preservation. `REPLACE` may suit UI display of corrupted data when best-effort recovery is desired, though telemetry should record that bytes were lost. `IGNORE` is rarely appropriate for security-sensitive data, identifiers, or signatures.

## 9. Does `InputStreamReader` Solve Everything?

`InputStreamReader` is a simple and solid choice for **byte-to-character streaming** with a known charset. It maintains an internal `CharsetDecoder` and will not corrupt Unicode merely because the underlying `InputStream` delivers fragmented bytes.

However, remember:

1. It does not auto-detect the charset of arbitrary files; specify it explicitly.
2. For UTF-8, it does not automatically strip every BOM according to a predictable application policy; if a leading BOM must be removed, write explicit logic.
3. It converts bytes into `char`/UTF-16 units. If the application slices `char[]` units separately and splits a surrogate pair, bugs can still occur at the **next layer** even though the byte decoder succeeded.
4. It does not parse JSON, XML, or length-prefixed protocols on its own.
5. It does not bound total characters read or protect memory if the application calls `readAllBytes` or concatenates strings unboundedly.
6. For parser APIs requiring exact byte offsets, a `Reader` can be awkward because one `char` does not map 1:1 to one byte.
7. For custom codecs or error policies, explicitly configuring a `CharsetDecoder` enables error reporting instead of silent replacement.

### Splitting a UTF-16 surrogate pair at the character layer

Example:

```java
String emoji = "😀";
char high = emoji.charAt(0);
char low = emoji.charAt(1);

System.out.println(emoji.length()); // 2
System.out.println(Character.isHighSurrogate(high)); // true
System.out.println(Character.isLowSurrogate(low));   // true
```

This is an illustrative Java snippet that can run inside `main`. If, after decoding UTF-8 properly, a program processes each `char` as an independent code point, it can still break emoji.

Text-layer solutions: use `String.codePoints()`, `Character.codePointAt`, or an iterator that carries a trailing high surrogate across `char[]` chunks. For splitting visible characters, handle grapheme clusters (Unicode segmentation) rather than only code points.

## 10. What Is a BOM?

A **Byte Order Mark (BOM)** originates from the Unicode symbol `U+FEFF` used at the start of some streams, primarily to indicate **endianness** or identify encoding. Not every Unicode file has a BOM, and a BOM is not security metadata.

Common leading byte sequences:

| Encoding / Characteristic | Leading Stream BOM |
|---|---|
| UTF-8 | `EF BB BF` |
| UTF-16 big-endian | `FE FF` |
| UTF-16 little-endian | `FF FE` |
| UTF-32 big-endian | `00 00 FE FF` |
| UTF-32 little-endian | `FF FE 00 00` |

**Note:** UTF-8 has no byte-order ambiguity; a UTF-8 BOM is an optional **signature**, not a requirement. Many formats/protocols forbid, ignore, or specify distinct rules for BOMs.

### A BOM must be at the start of the stream

If an application chooses to strip a BOM, detect it only at the **beginning of the content** (after establishing the appropriate source framing). Never run `text.replace("\uFEFF","")` across the entire text: that deletes every `U+FEFF` occurring mid-content even when not acting as a leading BOM.

A BOM can be split across chunk boundaries:

```text
UTF-8 BOM: EF BB BF
Chunk 1: EF
Chunk 2: BB
Chunk 3: BF 41 ...

Do not conclude "no BOM" simply because chunk 1 has fewer than three bytes.
```

Therefore, a custom BOM detector must **buffer enough leading bytes** before deciding, or decode continuously from the start and handle an initial `U+FEFF` character when permitted by the format.

## 11. UTF-8 BOM and Java `StandardCharsets.UTF_8`

When `StandardCharsets.UTF_8` decodes bytes `EF BB BF`, it normally emits the **character `U+FEFF`** in the string. Example:

```java
byte[] bytes = {
    (byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
    (byte) 0x41
};

String text = new String(bytes, StandardCharsets.UTF_8);
System.out.println(text.startsWith("\uFEFF")); // true
System.out.println(text.substring(1));          // A
```

This is an illustrative snippet requiring `StandardCharsets` and can be placed in `main`.

This causes a subtle bug: a configuration file has a UTF-8 BOM, the app expects header `"id,name"`, but the actual `String` is `"\uFEFFid,name"`. Matching the first column name fails even though both look identical to the naked eye.

Handling depends on the format:

- If the format **allows a BOM**, detect and strip it **once at the start**.
- If the format **forbids a BOM**, reject the input with a clear message instead of silently fixing it.
- If the format requires preserving exact original bytes, do not strip the BOM silently.
- If the application only displays text, make a consistent decision to avoid a hidden zero-width character at the start.

Do not insert a UTF-8 BOM into every file by default; standard UTF-8 does not need a BOM to decode properly.

## 12. UTF-16 BOM and Byte Order

UTF-16 has two endian-specific charsets, `UTF_16BE` and `UTF_16LE`; Java also provides `StandardCharsets.UTF_16`. They are not interchangeable in every situation.

- `UTF_16BE`: the two bytes of code unit `0x0041` are `00 41`.
- `UTF_16LE`: the two bytes are `41 00`.
- `UTF_16`: Java supports BOM detection to determine byte order (when present), falling back to this charset's default byte order when absent per implementation/documentation contract.

Example:

```text
Text "A"

UTF-16BE bytes (no BOM): 00 41
UTF-16LE bytes (no BOM): 41 00

With BOM:
UTF-16BE: FE FF 00 41
UTF-16LE: FF FE 41 00
```

If code uses `new String(bytes, UTF_16LE)` to read a file with a UTF-16BE BOM, the result will be garbled because little-endian was specified while the actual bytes are big-endian. Using `UTF_16` on data with a standard BOM lets the decoder detect the proper endianness.

### Do not check only the first two bytes rigidly

If a system supports both UTF-16 and UTF-32, BOM detection order matters because UTF-32LE's `FF FE 00 00` starts with `FF FE` (matching UTF-16LE's prefix). A custom detector should check the **longest BOM first**, combined with charsets permitted by the protocol. Java SE standardizes UTF-8/UTF-16 charsets; UTF-32 is not in the guaranteed `StandardCharsets` constant set across all environments, so do not assume `StandardCharsets.UTF_32LE` exists.

A well-designed application rarely **needs to auto-detect every Unicode encoding**. When a format specifies UTF-8, process it as UTF-8 and manage BOMs strictly according to that format's specification.

## 13. Do Not Confuse a BOM with Trusted Encoding Detection on Unknown Sources

"Having a BOM" does not guarantee the remaining content is valid. "Lacking a BOM" does not suffice to conclude a file is ASCII or UTF-8.

Common sources of error:

- The application uses `Charset.defaultCharset()` instead of the protocol's charset.
- A file written in Windows-1252 or a legacy code page is read as UTF-8.
- A BOM-less UTF-16LE file is read as UTF-8, yielding interleaved NULs or unexpected characters.
- A UTF-8 file with a BOM is parsed with the BOM stuck inside the first CSV column name.
- A file has corrupted or truncated trailing bytes, and a decoder with `REPLACE` hides evidence of the failure.
- A network protocol specifies a length prefix in **bytes**, yet the writer passes `String.length()`.
- HTTP/content metadata and actual payload disagree; the application must still follow the spec for handling them.

Never rely on heuristic guessing from a few bytes to assign a charset to security-sensitive data or data requiring full integrity. When reliable metadata is missing, establish an **explicit encoding contract/detection strategy** and validate at the business layer.

## 14. `CodingErrorAction`: `REPORT`, `REPLACE`, `IGNORE`

Java's `CharsetDecoder` can be configured as:

```java
CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

This is an illustrative snippet requiring imports for `CharsetDecoder`, `StandardCharsets`, and `CodingErrorAction`.

Comparison table:

| Policy | Behavior | When to Use |
|---|---|---|
| `REPORT` | Returns an error `CoderResult` / throws an exception when handled | Data requiring byte correctness, config files, protocols, testing |
| `REPLACE` | Inserts the decoder's replacement character | Best-effort display where data loss is acceptable |
| `IGNORE` | Drops invalid input | Only when business rules allow discarding data without breaking meaning |

### Malformed UTF-8

A byte sequence can be invalid because:

- A continuation byte appears without a valid leading byte.
- A leading byte requires additional continuation bytes, but an invalid byte follows.
- A sequence is truncated right at EOF.
- Bytes use an **overlong** encoding for a code point (forbidden by standard UTF-8).
- A sequence encodes surrogate code points or a code point outside the Unicode range.
- Bytes from another charset are mistakenly decoded as UTF-8.

Truncated-byte example:

```java
byte[] incomplete = {(byte) 0xE2, (byte) 0x98};
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT);

try {
    decoder.decode(ByteBuffer.wrap(incomplete));
} catch (MalformedInputException ex) {
    System.out.println("Truncated UTF-8 detected");
}
```

This is **illustrative code** requiring imports for `ByteBuffer`, `CharsetDecoder`, `CodingErrorAction`, and `MalformedInputException`. The `decode(ByteBuffer)` overload performs a complete single-shot decode, so the incomplete 2-byte prefix is flagged as malformed at the end of input. In streaming mode, calling `decode(input, output, false)` before EOF **waits** for the next byte instead of failing immediately.

### The Unicode replacement character is not merely cosmetic

If a program saves `�` into a file name, key, or signature instead of the original data, many things break:

- Byte hashes/checksums.
- User/resource name comparisons.
- JSON field names or CSV headers.
- Database queries and deduplication keys.
- Legal, financial, medical, or security-critical text content.

Therefore, whenever accuracy is required, handle errors with `REPORT` or verify the source encoding rather than turning bad input into "successfully decoded" text.

## 15. `ByteBuffer`: `flip`, `compact`, `clear`, and Boundary Bugs

`ByteBuffer` has three critical state fields: `capacity`, `position`, and `limit`.

### After reading bytes from I/O

Buffer in write mode:

```text
capacity = 8
position = 5
limit = 8
[41 E2 98 95 42 | ...]
```

`flip()` sets `limit` to the current `position` and resets `position` to 0 so the decoder reads valid bytes:

```text
position = 0
limit = 5
[41 E2 98 95 42 | ...]
```

### When the decoder has not consumed all bytes

Suppose the end of the buffer holds `E2 98`, missing `95`. After decoding, `position` points at the two unconsumed bytes.

`compact()` retains those two bytes, moves `position` to 2, and resets `limit` to `capacity`. The next I/O read appends bytes starting at index 2.

In this situation, `clear()` **does not preserve undecoded content**, allowing old bytes to be overwritten; this is a common root cause of `�` characters or flaky data loss that varies with buffer size.

### The decoder and `CharBuffer` also have their own boundaries

When the output `CharBuffer` is too small, `decode` returns `OVERFLOW`. Drain the output and call `decode` again. Do not misinterpret `OVERFLOW` as "file too large" or "invalid UTF-8 bytes".

If the output `CharBuffer` has space for only one UTF-16 unit while the next code point requires a two-unit surrogate pair, the decoder must return `OVERFLOW` rather than writing half an invalid pair. Size the buffer to fit at least a surrogate pair and always handle `OVERFLOW`.

## 16. Self-Diagnosis with Hex Dumps

When a character gets corrupted, logging the string from `new String(...)` destroys the evidence because invalid bytes have already been replaced. Inspect the **raw bytes** in a safe/test environment:

```java
byte[] data = "A☕B😀C".getBytes(StandardCharsets.UTF_8);
StringBuilder hex = new StringBuilder();

for (byte b : data) {
    if (!hex.isEmpty()) {
        hex.append(' ');
    }
    hex.append(String.format("%02X", b & 0xFF));
}

System.out.println(hex);
```

This snippet requires importing `StandardCharsets` and can run inside `main`. `StringBuilder.isEmpty()` is available on Java 17 (via `CharSequence`/`StringBuilder` APIs depending on runtime); to stay compatible with older environments, replace it with `hex.length() > 0`.

Output:

```text
41 E2 98 95 42 F0 9F 98 80 43
```

**Never log raw bytes of passwords, access tokens, or personal data in production**. For real incidents, prefer logging bounded metadata, offsets, expected charset, and byte samples redacted per policy.

### Diagnostic details to capture

- Configured encoding/charset on both writer and reader.
- File path/source ID, file size, and byte offset where the error was detected.
- Each chunk size and `ByteBuffer.position`/`limit`.
- Whether `CoderResult` was `UNDERFLOW`, `OVERFLOW`, or `MALFORMED`.
- Presence of a BOM; whether the BOM is at the start of the file or after a protocol prefix.
- `REPORT`/`REPLACE`/`IGNORE` policy.
- Whether data was gzipped/decompressed, decrypted, or transformed prior to decoding.
- Whether any code invokes `new String(chunk)` with the default charset.
- Whether any logic strips all `\uFEFF` or normalizes Unicode uncontrollably.

## 17. Diagnosing Byte Offsets vs Char Indexes

If an error occurs at byte offset 127, you cannot assume it maps to Java's `String.charAt(127)` when the data is UTF-8.

Example:

```text
Text: A☕B
UTF-8:
  A: byte offset 0, length 1
  ☕: byte offset 1, length 3
  B: byte offset 4, length 1

Java UTF-16 char indexes:
  A index 0
  ☕ index 1
  B index 2
```

For supplementary-plane emoji, the divergence is even greater because 4 UTF-8 bytes → 2 UTF-16 units → 1 code point.

When reporting parser errors, state explicitly whether an offset is:

- **Byte offset** in the file/wire stream.
- **UTF-16 char index** in the Java `String`.
- **Code point index** in the content.
- **Logical line/column** if the parser defines newline and Unicode conventions.

If a binary protocol uses a byte length prefix, encode first to measure the length, and have the reader read that exact byte count before decoding **the payload**—never compute it with `String.length()`.

## 18. Byte Length in Network Protocols

Classic mistake:

```java
String body = "Cà phê ☕";
int declaredLength = body.length();   // Wrong if the protocol requires a byte count.
byte[] wire = body.getBytes(StandardCharsets.UTF_8);
```

If a protocol frames messages as `[4-byte payload length][payload bytes]`, the length must be `wire.length`, not `body.length()`.

Correct pattern (illustrative code):

```java
byte[] bodyBytes = body.getBytes(StandardCharsets.UTF_8);
if (bodyBytes.length > MAX_PAYLOAD_BYTES) {
    throw new IOException("Frame too large");
}
frame.putInt(bodyBytes.length);
frame.put(bodyBytes);
```

Variables `body`, `MAX_PAYLOAD_BYTES`, and `frame` must be declared/allocated with sufficient capacity beforehand, and `frame` must use the `ByteOrder` agreed upon with the peer. On the reading side, use the declared byte length, read the complete frame (handling partial I/O), and decode **after all bytes have arrived**. Even if a frame is split across TCP packets or file chunks, the encoding retains clear logical boundaries.

If a protocol uses text delimiters such as newlines, you must also decide escaping rules, handling of `\r\n` split across buffers, and maximum line lengths. **Network I/O boundaries do not automatically align with record or Unicode character boundaries**.

## 19. Unicode Normalization: Visually Identical Does Not Mean Byte-Equal

Two strings can render identically yet have different Unicode encodings:

```java
String a = "\u00E9";
String b = "e\u0301";

System.out.println(a.equals(b)); // false

String na = Normalizer.normalize(a, Normalizer.Form.NFC);
String nb = Normalizer.normalize(b, Normalizer.Form.NFC);
System.out.println(na.equals(nb)); // true
```

This is an illustrative snippet requiring `import java.text.Normalizer;` and runs inside a Java 17 method.

- **NFC** attempts to compose canonical equivalents per the Unicode standard.
- **NFD** performs canonical decomposition.
- `NFKC`/`NFKD` apply compatibility mappings, which can change the visual form or meaning of certain characters beyond canonical normalization.
- Never silently normalize data such as identifiers, passwords, or signed strings unless specified by the protocol.
- Do not treat normalization as full protection against homograph, spoofing, or confusable-character attacks.

To test Vietnamese data, include both precomposed forms and combining marks, test byte round-trips when verbatim preservation is required, and test normalization separately per business rules.

## 20. Minimum Test Cases for Unicode Streaming

A test suite should include these strings and scenarios:

| Test Case | What It Proves |
|---|---|
| ASCII `Hello` | No multibyte bytes needed, baseline |
| Vietnamese `Cà phê` | Non-ASCII Unicode |
| `☕` split after byte 1 and byte 2 | Decoder retains 1–2 incomplete bytes |
| `😀` split after byte 1, 2, and 3 | Decoder retains up to 3 leading bytes |
| UTF-8 BOM `EF BB BF` split into 3 chunks | BOM policy applied exactly once |
| No BOM | Does not accidentally strip the first character |
| `U+FEFF` in the middle of content | Does not delete every `U+FEFF` |
| UTF-16BE/LE with BOM | Correct endianness per format |
| UTF-16LE without BOM | Decodes properly only when charset is known |
| UTF-8 input missing final byte | `REPORT` catches truncated input at EOF |
| Lone continuation byte `80` | Malformed input caught properly |
| Full output buffer | `OVERFLOW` drained with no lost characters |
| Decoder fed chunks of size 1, 2, 3, 4, 7... | Output invariant across chunking strategies |
| String with combining accents | Does not confuse `equals` with canonical equivalence |
| Emoji with surrogate pair | Not split when slicing Java `char[]` |
| Length-prefixed UTF-8 protocol | Length measured in bytes, not `String.length` |

### Property-style test: invariance across chunk boundaries

A strong invariant:

> Given the same valid UTF-8 byte sequence, a stateful decoder's output must be identical regardless of how the input is partitioned into 1-, 2-, 3-, ... byte chunks (provided byte order is preserved and EOF is signaled accurately).

You can write tests looping over different fixed chunk sizes, then add randomized partition tests. You do not need "one packet = one message" to decode text properly.

Likewise, for invalid UTF-8 sequences, the **error policy** must be consistent: `REPORT` flags malformed/truncated input, while `REPLACE` produces deterministic output per replacement policy; never silently accept bad data simply because the split landed on a different boundary.

## 21. BOMs and Inputs with a Binary Prefix/Header

In some protocols, the byte stream begins with a **binary header** followed by a text field. In that case, a BOM (if allowed by spec) must be checked **at the start of the text field**, not necessarily at offset 0 of the entire stream.

Example:

```text
[magic: 4 bytes][version: 1][textLength: 4][text UTF-8 bytes]
```

If `text UTF-8 bytes` starts with `EF BB BF`, the BOM policy applies after the parser has read the header and located the payload. If the parser wraps the entire byte stream in `InputStreamReader` starting at byte 0, the binary header may be decoded into bogus characters and shift byte offsets.

Therefore:

1. Parse the **binary structure** in bytes first.
2. Determine the byte range of the text payload.
3. Select the charset from spec/metadata.
4. Apply the appropriate BOM policy at the **start of the payload**.
5. Decode the exact range with a stateful decoder, or read all field bytes and decode once.

Never assume every `EF BB BF` appearing inside a payload is a BOM; it could also be an intentional `U+FEFF` character in the content.

## 22. When Is Independent Per-Chunk Decoding Valid?

Not every chunked decode is wrong. If **the protocol defines each chunk as an independent, self-contained UTF-8 string** with an explicit length prefix and the sender guarantees it never splits an encoding sequence, each message can be decoded individually.

Example:

```text
Frame 1: [length=3]["☕" UTF-8 3 bytes]
Frame 2: [length=4]["😀" UTF-8 4 bytes]
```

The reader must read all 3 or 4 bytes before creating the `String`. If the network layer splits a frame across multiple reads, accumulate **all frame bytes** first. What may be decoded independently is a **protocol-defined message boundary**, not an arbitrary socket/file buffer boundary.

Some text protocols like JSON Lines use explicit delimiters; the parser must identify delimiters per the charset and enforce line length limits. With multi-byte Unicode characters, a continuation byte cannot be mistaken for a newline inside a UTF-8 multi-byte sequence; still, verify the parser does not confuse framing and encoding under a different byte order.

## 23. Common Mistakes and Fixes

1. **`new String(buffer, 0, n, UTF_8)` on every byte read and concatenating.** Fails when a code point is split; use `InputStreamReader` or a stateful `CharsetDecoder`.
2. **Using `String.length()` as the byte count written to the wire.** Wrong for UTF-8; encode first and use `byte[].length`.
3. **Treating Java `char` as a code point.** False for surrogate pairs; use `codePoints()` or appropriate `Character` APIs.
4. **Calling `ByteBuffer.clear()` when the decoder returns `UNDERFLOW` with leftover bytes.** Drops bytes; use `compact()`.
5. **Forgetting `flip()` before decoding.** The decoder reads the wrong range or reads nothing.
6. **Not draining `CharBuffer` after `OVERFLOW`.** The loop stalls or drops output.
7. **Calling `decode(..., true)` after every chunk.** When a chunk ends mid-code-point, the decoder mistakes it for EOF and reports malformed input.
8. **Forgetting `flush` after `decode(..., true)`.** For stateful decoders, trailing output/finalization steps can be lost.
9. **Sharing one `CharsetDecoder` across multiple streams concurrently.** A decoder holds state and cannot be shared arbitrarily across streams or threads.
10. **Not calling `reset()` on a decoder before reusing it for a new independent stream.** Leftover state invalidates decoding.
11. **Treating `CodingErrorAction.REPLACE` as accurate data transfer.** Replacement loses information and cannot be used where round-trip fidelity is needed.
12. **Ignoring malformed bytes (`IGNORE`) without evaluating business impact.** Can alter identifiers or headers silently.
13. **Assuming every Unicode file has a BOM.** UTF-8 BOMs are optional and forbidden by many formats.
14. **Stripping `U+FEFF` everywhere.** If stripping is needed, handle only the leading position per spec.
15. **Confusing UTF-16BE and UTF-16LE BOMs.** Wrong endianness turns content into garbage.
16. **Checking UTF-16 before UTF-32 when supporting both.** UTF-32LE's BOM shares the `FF FE` prefix of UTF-16LE; use longest-match rules.
17. **Assuming raw UTF-8 bytes of NFC and NFD are identical.** They can render identically while differing in bytes and code points.
18. **Relying on logged decoded strings to inspect bad bytes.** Replacement hides the original bytes; inspect safe hex dumps.
19. **Reading an entire untrusted file with `readAllBytes` before decoding.** Risk of OOM; stream with quotas.
20. **Assuming `InputStreamReader` returns intact grapheme clusters per `read(char[])`.** Readers return `char` units; downstream code must still handle surrogates/graphemes when slicing `char[]`.
21. **Not checking final EOF.** Truncated UTF-8 only surfaces once you confirm no more bytes remain.
22. **JSON/XML/CSV parsers disagreeing on charset between writer and reader.** Determine from spec, not random environment defaults.
23. **Normalizing all text without checking the contract.** Can break signatures, identifiers, or byte-preserved data.
24. **Guessing charset from file extension.** File names do not guarantee content encoding.
25. **Assuming network reads match message boundaries.** TCP is a byte stream; frame explicitly.

## 24. Practice Exercises

**Exercise 1 — Varying chunk sizes.** Modify `UnicodeBoundaryDemo` from 2 bytes/turn to 1, 3, 4, and 5 bytes/turn. Prove `Split-safe equals: true` in all runs when the file and charset match. Do not create a new decoder per iteration.

**Exercise 2 — Corrupting the final byte.** Take the UTF-8 bytes of `"😀"` and drop the last byte. Use `CharsetDecoder` with `REPORT`, pass `decode(..., true)` at EOF, and assert the malformed error. Then try `REPLACE` to observe the non-original output.

**Exercise 3 — UTF-8 BOM split across three reads.** Write bytes `EF BB BF 41` using an `InputStream` returning only 1 byte at a time. Ensure the detector does not mistake a lone `EF` for a complete BOM, and that post-policy output is `A`.

**Exercise 4 — UTF-16BE and UTF-16LE.** Generate byte sequences of `"A☕"` using `UTF_16BE` and `UTF_16LE`. Compare hex, decode with the right charset, then decode with the wrong one to observe the difference.

**Exercise 5 — Surrogate pair.** Read an emoji into Java `char[]`. Split the `char[]` right between high and low surrogates, then design a code point processor that carries the high surrogate to the next chunk.

**Exercise 6 — Binary length prefix.** Implement a `int32 byteLength + UTF-8 payload` protocol. Send `"Cà phê ☕"`, split the payload across randomized reads, and verify the final `String` equals the original.

**Exercise 7 — Normalization.** Compare `"\u00E9"` and `"e\u0301"` on `equals`, code point count, UTF-8 bytes, and result after `Normalizer.Form.NFC`.

**Exercise 8 — Diagnostics.** On detecting malformed UTF-8, log the expected charset, byte offset, and **redacted** hex bytes without logging full sensitive content. Write tests for bytes `80` and `E2 98`.

## 25. Self-Check Questions

**Question 1.** Reading `E2 98` and ending **a single read**—is that enough reason to report corrupted UTF-8?  
**No**, if the byte stream has not reached EOF. It may be a valid prefix of a three-byte code point. The decoder must wait for the next byte.

**Question 2.** If **true EOF** has been reached with only `E2 98` left, what is the strict decoding result?  
**Malformed input**, because the sequence is incomplete.

**Question 3.** Why can `new String(chunk1, UTF_8) + new String(chunk2, UTF_8)` fail?  
**Because each independent decoder** forgets leading bytes of a code point residing in the previous chunk.

**Question 4.** How does `ByteBuffer.compact()` help in an incremental decoder?  
**It preserves unconsumed bytes** while waiting for the next chunk and frees trailing space for appending.

**Question 5.** Does `CoderResult.OVERFLOW` mean the UTF-8 data is invalid?  
**No.** It usually means the output `CharBuffer` is full and needs to be drained before decoding continues.

**Question 6.** Does `"😀"` have `length() == 1`?  
**No**. `String.length() == 2` due to the UTF-16 surrogate pair, though it has 1 Unicode code point.

**Question 7.** Which bytes make up the UTF-8 BOM?  
**EF BB BF**. UTF-8 does not need a BOM to determine endianness.

**Question 8.** Does Java's UTF-8 decoder always strip a leading `EF BB BF` automatically?  
**No**. Many standard decoding APIs turn it into the `U+FEFF` character; an explicit policy is needed.

**Question 9.** Should you call `text.replace("\uFEFF","")` to handle a BOM?  
**Not by default**, because it deletes `U+FEFF` everywhere. A BOM belongs at the **start of a stream/field**, not every `U+FEFF` character.

**Question 10.** A protocol sends a UTF-8 string with a byte length prefix. Can you use `String.length()`?  
**No**; encode first and measure the actual byte count.

**Question 11.** Does `InputStreamReader` decoding UTF-8 across byte chunks automatically guarantee `read(char[])` calls never split a surrogate pair?  
**Do not rely on that**; the layer handling `char` units must still account for code point/grapheme boundaries.

**Question 12.** Why is `REPORT` useful when testing input data?  
**It surfaces encoding errors clearly**, instead of silently inserting replacements and letting corrupted data pass as valid.

**Question 13.** Do two strings that look like `é` necessarily have the same UTF-8 bytes?  
**No**. One can be `U+00E9` while the other is `U+0065 U+0301`.

**Question 14.** When supporting both UTF-16 and UTF-32 BOMs, why check the longest BOM first?  
**To avoid misinterpreting the `FF FE` prefix of UTF-32LE** as a complete UTF-16LE BOM.

## 26. Implementation and Testing Checklist

- [ ] Identify the exact charset from the protocol or trusted metadata, preferring UTF-8 when permitted by spec.
- [ ] Specify encoding explicitly on both writer and reader; never rely on the default charset.
- [ ] Distinguish byte offset, Java UTF-16 index, code point, and grapheme.
- [ ] Never decode individual byte chunks unless guaranteed to hold a complete message.
- [ ] For simple text streams, use `InputStreamReader`/`BufferedReader` with the same charset.
- [ ] For binary protocols/`ByteBuffer`, use a stateful `CharsetDecoder` and retain leftover bytes via `compact()`.
- [ ] Ensure `decode(..., true)` is called **only at EOF**, followed by `flush` per protocol.
- [ ] Drain the output buffer on `OVERFLOW` without losing bytes or input state.
- [ ] Choose `REPORT` for data requiring accuracy; log and handle errors explicitly.
- [ ] Enforce byte/character/CPU limits and timeouts suitable for the trust level of the source.
- [ ] Define a BOM policy: allow, strip at start, or reject per format.
- [ ] For UTF-16, specify BE/LE; do not guess BOMs when the format fixes the charset.
- [ ] Do not blindly strip `U+FEFF` in the middle of content.
- [ ] In network framing, compute length in bytes after encoding.
- [ ] Test with Vietnamese, emoji, combining marks, UTF-8 BOM, and EOF mid-code-point.
- [ ] Test all small chunk sizes: 1, 2, 3, 4, ... bytes and random splits.
- [ ] Compare byte round-trips when exact preservation is required.
- [ ] Normalize only according to contract; never silently turn NFD into NFC when disallowed.
- [ ] Define behavior for malformed bytes and wrong encodings.
- [ ] Never log sensitive raw data in diagnostic messages.

## 27. Summary

- **Unicode is a set of code points; UTF-8/UTF-16 are ways to represent them in storage/transmission units.**
- **One byte read does not equal one Unicode character.** UTF-8 uses 1–4 bytes per code point, so sequences must be allowed to span chunks.
- **Never call `new String` independently on arbitrary chunks.** Use `InputStreamReader` or a stateful `CharsetDecoder`.
- **`flip()` switches to reading; `compact()` retains incomplete bytes; `clear()` can lose them.**
- **Signal EOF only when the stream ends**, run the final decode + flush, and report malformed input if truncated.
- **The UTF-8 BOM is EF BB BF**, optional; UTF-16 BOMs indicate endianness. BOM policies follow the format and apply only at the start of the stream/payload.
- **Byte count ≠ `String.length()` ≠ code point count**, especially with Vietnamese, emoji, and combining marks.
- **Boundary and error-policy testing are mandatory** so corrupted data is never silently turned into replacement characters unnoticed.

### Java SE 17 API Documentation

- [CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [CoderResult](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CoderResult.html)
- [CodingErrorAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [InputStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html)
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
