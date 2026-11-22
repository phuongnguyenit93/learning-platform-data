# Unicode Data, BOMs, and Characters Split Across Chunks in Java I/O

## 1. The Problem to Solve

When a Java application reads or writes text, it does not literally transfer "characters" over disk or a socket. It transfers **bytes**. Those bytes must be encoded or decoded according to a specific **charset**, such as UTF-8 or UTF-16.

A program may handle ASCII text fine yet corrupt Vietnamese characters, emojis, or personal names when it:

- Splits a file or network stream into **byte chunks** and calls `new String(chunk, UTF_8)` on **each individual chunk**.
- Reads the bytes of a multi-byte UTF-8 character across separate read calls.
- Confuses **bytes**, **UTF-16 code units**, **Unicode code points**, and **user-perceived characters**.
- Fails to recognize a **BOM** (Byte Order Mark) at the start of a file.
- Decodes UTF-16 with the wrong byte order.
- Replaces invalid bytes with `�` without detecting that the source data is corrupted.
- Confuses the byte count in network framing with `String.length()`.
- Slices a buffer at an arbitrary position and treats it as a character boundary.

This lesson sits in the **Testing and Diagnostics** module of Java Core I/O: besides decoding correctly, we will design boundary test cases, hex byte dumps, error-policy checks, BOM handling, and Unicode normalization checks.

**Central principle:** The boundary of a single `InputStream.read(...)`, `FileChannel.read(...)`, or network packet **is not** a Unicode character boundary. Decoding must preserve **continuous state** across incoming byte chunks.

## 2. Unicode Is Not Synonymous with UTF-8

### Unicode Code Points

Unicode defines **code points**, usually written as `U+XXXX`. For example:

| Content | Unicode Code Point | UTF-8 | UTF-16 |
|---|---|---|---|
| `A` | `U+0041` | `41` | `0041` |
| `é` | `U+00E9` | `C3 A9` | `00E9` |
| `☕` | `U+2615` | `E2 98 95` | `2615` |
| `😀` | `U+1F600` | `F0 9F 98 80` | `D83D DE00` (surrogate pair) |

The UTF-16 sequences in the table are **code unit values**; their actual bytes also depend on big-endian/little-endian byte order.

### UTF-8 Is a Variable-Length Encoding

In UTF-8, a valid Unicode code point occupies **1 to 4 bytes**. The bytes of a single code point **can land in two different read chunks**.

Example with `☕`:

```text
Unicode code point: U+2615

UTF-8 bytes: E2 98 95
             ^^ ^^ ^^
             1  2  3

Chunk #1: E2 98
Chunk #2: 95

Neither individual chunk is enough to decode U+2615.
```

If a developer calls `new String(chunk1, UTF_8)` and `new String(chunk2, UTF_8)` and concatenates the two strings, each decode treats that chunk's bytes as a standalone broken sequence, producing replacement characters `U+FFFD`.

### UTF-16 Is a 16-Bit Code Unit Encoding

In Java, `String` uses a sequence of **UTF-16 code units** to represent content (the `char` type corresponds to one code unit). A supplementary-plane code point, such as `😀`, requires **two code units**:

```text
U+1F600 -> high surrogate D83D + low surrogate DE00

Java "😀".length() == 2
"😀".codePointCount(0, "😀".length()) == 1
```

In a UTF-16 file, each code unit consists of two bytes; reading it properly requires knowing **endianness**, as well as handling surrogate pairs. A file can also be split right **between the two bytes of a code unit**, or **between the two surrogates**.

## 3. Four Counting Units Frequently Confused

Consider the string:

```java
String text = "A☕B😀C";
```

The different quantities:

| Metric | Value | Explanation |
|---|---:|---|
| `text.getBytes(UTF_8).length` | 10 | 1 + 3 + 1 + 4 + 1 UTF-8 bytes |
| `text.length()` | 6 | Number of UTF-16 code units; the emoji takes 2 |
| `text.codePointCount(0,text.length())` | 5 | Number of Unicode code points |
| User-perceived grapheme clusters | 5 for this example | Not always equal to code points |

**Never use `String.length()` as the byte size to send**, never slice a byte stream by character count, and never treat a Java `char` as always being a complete Unicode character.

Example of combining accented characters:

```text
"é"        U+00E9            (one code point)
"e\u0301"  U+0065 U+0301     (two code points)

Two strings can look almost identical yet have different representations.
```

These two representations can have different UTF-8 byte counts, `String.equals` is not necessarily true, and normalization may be considered depending on business rules.

For complex emojis with zero-width joiners, variation selectors, or combining marks, "one visible character" can consist of **multiple** code points. Never assume `codePointCount` always equals the number of grapheme clusters.

## 4. A Single `read()` Does Not Guarantee a Complete Character

I/O APIs normally return the actual number of bytes received:

```java
int n = inputStream.read(buffer);
```

A single read can return **fewer bytes than the buffer length**, even when the source still has plenty of data, depending on stream type and timing. Over a network socket, one `send` by the peer does not correspond to one `read` in the receiving application.

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

No I/O event says "this is one Unicode character." Chunk boundaries are determined solely by buffer size, providers, and data arrival timing.

### Anti-pattern: Decoding Each Chunk Independently

```java
byte[] buffer = new byte[2];
StringBuilder text = new StringBuilder();

int n;
while ((n = input.read(buffer)) != -1) {
    text.append(new String(buffer, 0, n, StandardCharsets.UTF_8));
}
```

This is **code illustrating a Unicode bug**, assuming `input` is an `InputStream`. Each `new String` call creates **an independent decoding session**, forgetting that the trailing byte `E2` of the previous chunk still needed `98 95` in the next chunk.

Choosing a larger buffer **reduces the probability** of splitting a character in some tests, but **does not solve the root cause**. Any finite buffer can end in the middle of a character.

## 5. Simplest Approach: Use a `Reader` with an Explicit Charset

If the goal is **reading text** without managing custom byte framing, use `InputStreamReader` or `Files.newBufferedReader` with the proper charset:

```java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {

    String line;
    while ((line = reader.readLine()) != null) {
        // Process the complete Unicode line properly assembled by the decoder.
    }
}
```

This is an illustrative snippet requiring `BufferedReader`, `Files`, `Path`, and `StandardCharsets`; `path` must be declared.

`InputStreamReader` maintains **decoder state across character reads**. If a UTF-8 code point is split across multiple underlying byte reads, the reader retains the incomplete portion and waits for the remaining bytes instead of decoding each byte chunk as a standalone string.

### Specifying the Charset Explicitly

```java
try (Reader reader = new InputStreamReader(
        Files.newInputStream(path), StandardCharsets.UTF_8)) {
    char[] chars = new char[256];
    int n;
    while ((n = reader.read(chars)) != -1) {
        // Use the exact n UTF-16 code units.
    }
}
```

A `Reader` returns **UTF-16 code units** into `char[]`, not "exact `n` code points." Even though the UTF-8 decoder handles split multi-byte sequences properly, **a surrogate pair in `char[]` can still be split across character reads** if the buffer or read chunk fills up or stops right at that boundary.

If the task only displays or rewrites text, characters can stay in the reader/writer pipeline. If you must count code points, split tokens/graphemes, or validate surrogates, use appropriate Unicode APIs rather than treating every `char` element as standalone.

## 6. `CharsetDecoder`: Continuous Decoding with `ByteBuffer`

When an application handles a **binary protocol**, `ByteBuffer`, or streams arriving in arbitrary segments, `java.nio.charset.CharsetDecoder` gives full control over decoding.

Components:

- `CharsetDecoder`: maintains decoding state across calls.
- `ByteBuffer` input: holds newly arrived bytes **plus any leftover partial character bytes from the previous pass**.
- `CharBuffer` output: receives decoded UTF-16 code units.
- `CoderResult.UNDERFLOW`: the decoder consumed all it can from current input; incomplete trailing bytes may remain.
- `CoderResult.OVERFLOW`: the output buffer is full; drain `CharBuffer` and continue decoding.
- `CoderResult.isError()`: invalid or unmappable bytes according to the charset and error policy.
- `decoder.decode(input, output, endOfInput)`: pass `true` only once the byte stream has truly ended.
- `decoder.flush(output)`: finalizes trailing state **after `decode(..., true)` has returned `UNDERFLOW`**.

### Standard Buffer Cycle

```text
ByteBuffer in WRITE MODE
     |   (may still contain bytes from the end of the previous pass)
     +-- append new bytes
     |
     v
input.flip()  -> READ MODE
     |
     v
decoder.decode(input, chars, eof)
     |
     +-- OVERFLOW -> chars.flip(), drain, chars.clear(), continue decoding
     |
     +-- ERROR -> throwException / error policy
     |
     +-- UNDERFLOW -> retain unconsumed bytes
     |
input.compact() -> move incomplete bytes to the front, return to WRITE MODE
     |
     +-- if not EOF: read more bytes into remaining space, loop
     |
     +-- if EOF: decoder.flush(chars) until UNDERFLOW
```

`ByteBuffer.compact()` is the core mechanism. It **does not discard remaining bytes**: it copies unprocessed bytes in `[position, limit)` to the start of the buffer and places `position` right after them. The next I/O read simply appends new bytes behind them.

Never call `input.clear()` after every `UNDERFLOW`: `clear()` allows overwriting the entire input buffer and **drops pending bytes**.

## 7. Complete Java 17+ Example: Reading UTF-8 in 2-Byte Chunks

The program below:

1. Creates a temporary file containing `A☕B😀C` encoded in UTF-8.
2. Reads **at most 2 bytes** per read, deliberately slicing inside the byte encodings of `☕` and `😀`.
3. Uses a single `CharsetDecoder` throughout, retaining leftover bytes with `compact()`.
4. Verifies the round-trip and compares byte count, UTF-16 code unit count, and code point count.
5. Rewrites the file with a leading **UTF-8 BOM** to demonstrate that a standard decoder sees `U+FEFF` as a character and how to handle BOMs by policy.
6. Closes and deletes the temporary file.

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
                    // OVERFLOW: outputChars has been drained, continue decoding.
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
                // OVERFLOW: characters remain in decoder, keep draining.
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

Compile and run with JDK 17 or higher:

```bash
javac UnicodeBoundaryDemo.java
java UnicodeBoundaryDemo
```

**Exact expected stdout when temporary file I/O succeeds:**

```text
UTF-8 bytes: 10
UTF-16 units: 6
Code points: 5
Split-safe equals: true
Leading BOM character: true
After BOM policy: A☕B😀C
```

Why is this example correct?

- `inputBytes` in write mode accepts at most 2 bytes per turn. When encountering the first 2 bytes of `☕`, the decoder returns `UNDERFLOW` and does not treat them as an error because `endOfInput` is not yet true.
- `inputBytes.compact()` preserves the undecoded bytes. The next turn appends the third byte, completing `E2 98 95`.
- Likewise for the 4-byte UTF-8 character `😀`. The decoder can hold leading bytes across multiple passes until all bytes arrive.
- `outputChars` holds decoded UTF-16 results. `StringBuilder.append(CharBuffer)` appends the decoded code units.
- `CodingErrorAction.REPORT` ensures genuinely invalid bytes or truncated trailing sequences throw an error rather than silently inserting `�`.
- `endOfInput=true` **only when `read` has returned `-1`**. Passing `true` prematurely when a chunk holds incomplete bytes causes the decoder to treat leftover bytes as malformed.
- After the final decode, `decoder.flush` completes decoder state per the protocol.
- `rawWithBom` begins with `U+FEFF` decoded from `EF BB BF`. The example policy strips only **the leading `U+FEFF` character**; it does not delete every occurrence inside the body.

**Intentional limitations:** the example uses small buffers, a tiny file, and a `StringBuilder` to make the mechanism clear. In production with very large files or untrusted sources, enforce output limits, manage rate/timeouts, and process decoded characters incrementally rather than accumulating everything in one `StringBuilder`.

## 8. Deep Dive into `CharsetDecoder` States

### UNDERFLOW

`UNDERFLOW` typically means the decoder **cannot make further progress** with the provided input. In streaming mode, `ByteBuffer` may still hold 1–3 leading bytes of an incomplete UTF-8 sequence. Keep them using `compact()`.

Example:

```text
Input bytes: E2 98
Decoder: UNDERFLOW
input.remaining(): 2 (unconsumed)
compact(): keeps E2 98
append next: 95
decode again: -> ☕
```

When `endOfInput=true`, incomplete trailing bytes at EOF can no longer wait for more input: they must be handled according to the malformed-input policy.

### OVERFLOW

`OVERFLOW` does not mean the file is too large or bytes are corrupted. It means **`CharBuffer` lacks space for the next UTF-16 code units**. Handle it by draining:

```java
outputChars.flip();
process(outputChars);
outputChars.clear();
```

This is an illustrative snippet where `process` is application-defined. After draining, call `decode` again **on the input at its current position**—never discard remaining input or create a new decoder.

### ERROR

`CoderResult.isError()` covers malformed-input or unmappable-character conditions according to the charset and error policy:

- `REPORT`: returns an error result; `throwException()` converts it into an appropriate checked exception, such as `MalformedInputException`.
- `REPLACE`: inserts the decoder's replacement string/character and continues.
- `IGNORE`: drops the invalid input, risking silent data loss without trace.

`REPORT` is usually appropriate when testing data pipelines, reading config files, decoding schema-governed protocols, or handling content needing exact preservation. `REPLACE` may suit UI display of damaged data when "best effort" recovery is desired, provided telemetry records that bytes were lost. `IGNORE` is rarely appropriate for security-relevant data, identifiers, or signatures.

## 9. Does `InputStreamReader` Solve Everything?

`InputStreamReader` is a simple and solid choice for **byte-to-character streaming** with a known charset. It manages an internal `CharsetDecoder` and will not corrupt Unicode merely because the underlying `InputStream` delivers bytes in small chunks.

However, remember:

1. It does not auto-detect the charset of arbitrary files; specify it explicitly.
2. With UTF-8, it does not automatically strip BOMs according to a predictable application policy; if leading BOM removal is needed, write explicit logic.
3. It converts bytes into `char`/UTF-16 units. If the application processes `char[]` slices and splits a surrogate pair, bugs can still arise at the **next layer** even though the byte decoder worked properly.
4. It does not parse JSON, XML, or length-prefixed protocols.
5. It does not cap total characters read or protect memory if the application calls `readAllBytes` or builds unbounded strings.
6. For parser APIs requiring exact byte offsets, `Reader` can be awkward because one `char` does not map 1:1 to one byte.
7. For custom codecs or strict error policies, explicitly creating a `CharsetDecoder` helps fail fast instead of silently substituting characters.

### Splitting a UTF-16 Surrogate Pair at the Character Layer

Example:

```java
String emoji = "😀";
char high = emoji.charAt(0);
char low = emoji.charAt(1);

System.out.println(emoji.length()); // 2
System.out.println(Character.isHighSurrogate(high)); // true
System.out.println(Character.isLowSurrogate(low));   // true
```

This is an illustrative Java snippet you can place in `main`. Even after decoding UTF-8 properly, a program that treats every `char` as an independent code point can still break emojis.

Text-layer solution: use `String.codePoints()`, `Character.codePointAt`, or an iterator that carries a trailing high surrogate across `char[]` chunks. For user-visible character segmentation, handle grapheme clusters (Unicode segmentation) rather than only code points.

## 10. What Is a BOM?

A **Byte Order Mark (BOM)** originates from the Unicode character `U+FEFF` placed at the beginning of some streams, primarily to indicate **endianness** or identify encoding. Not all Unicode files have a BOM, and a BOM is not security metadata.

Common leading byte sequences:

| Encoding / Characteristic | Leading Stream BOM |
|---|---|
| UTF-8 | `EF BB BF` |
| UTF-16 big-endian | `FE FF` |
| UTF-16 little-endian | `FF FE` |
| UTF-32 big-endian | `00 00 FE FF` |
| UTF-32 little-endian | `FF FE 00 00` |

**Note:** UTF-8 has no byte-order ambiguity; a UTF-8 BOM is an optional **signature**, not a requirement. Many formats and protocols forbid, ignore, or handle BOMs under specific rules.

### A BOM Must Be at the Start of the Stream

If an application chooses to strip a BOM, detect it only at the **beginning of the content** (after resolving appropriate source framing). Never run `text.replace("\uFEFF","")` across the entire text: you would erase every `U+FEFF` inside the body even when it was not a leading stream BOM.

A BOM can be split across chunk boundaries:

```text
UTF-8 BOM: EF BB BF
Chunk 1: EF
Chunk 2: BB
Chunk 3: BF 41 ...

Do not decide "no BOM" just because chunk 1 does not yet have three bytes.
```

Therefore, a custom BOM detector must **buffer enough leading bytes** before deciding, or decode continuously from the start and handle an initial `U+FEFF` character when allowed by the format.

## 11. UTF-8 BOM and Java `StandardCharsets.UTF_8`

When decoding bytes `EF BB BF`, `StandardCharsets.UTF_8` normally yields **character `U+FEFF`** in the resulting string. Example:

```java
byte[] bytes = {
    (byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
    (byte) 0x41
};

String text = new String(bytes, StandardCharsets.UTF_8);
System.out.println(text.startsWith("\uFEFF")); // true
System.out.println(text.substring(1));          // A
```

This is an illustrative snippet requiring `StandardCharsets` that can run in `main`.

This causes a subtle bug: a configuration file has a UTF-8 BOM, the application expects header `"id,name"`, but the actual `String` is `"\uFEFFid,name"`. Comparing the first column name fails even though both look identical to the human eye.

Handling depends on the format:

- If the format **allows a BOM**, detect and strip it **once at the beginning**.
- If the format **forbids a BOM**, reject the input with a clear message rather than silently fixing it.
- If the format requires exact byte preservation, do not strip the BOM silently.
- If the application only displays text, enforce a consistent policy to avoid hidden leading zero-width characters.

Do not insert a UTF-8 BOM into every file by default; standard UTF-8 does not need a BOM to decode properly.

## 12. UTF-16 BOM and Byte Order

UTF-16 has two endian-specific charsets, `UTF_16BE` and `UTF_16LE`; Java also provides `StandardCharsets.UTF_16`. They are not interchangeable in every situation.

- `UTF_16BE`: the two bytes of code unit `0x0041` are `00 41`.
- `UTF_16LE`: the two bytes are `41 00`.
- `UTF_16`: Java supports BOM detection to determine byte order when present, and uses this charset's default byte order when absent according to the implementation/documentation contract.

Example:

```text
Text "A"

UTF-16BE bytes (no BOM): 00 41
UTF-16LE bytes (no BOM): 41 00

With BOM:
UTF-16BE: FE FF 00 41
UTF-16LE: FF FE 41 00
```

If code uses `new String(bytes, UTF_16LE)` to read a file with a UTF-16BE BOM, the result is wrong; you forced little-endian while the bytes are actually big-endian. Using `UTF_16` on data with a standard BOM lets the decoder detect the appropriate endianness.

### Do Not Naively Check Only the First Two Bytes

If a system supports both UTF-16 and UTF-32, BOM detection order matters because UTF-32LE's `FF FE 00 00` begins with `FF FE` (sharing a prefix with UTF-16LE). A custom detector should match the **longest BOM first**, combined with charsets allowed by the protocol. Java SE includes standard UTF-8/UTF-16 charsets; UTF-32 is not among the required `StandardCharsets` constants in every environment, so do not assume `StandardCharsets.UTF_32LE` exists.

A well-designed application usually **does not need to auto-detect every Unicode encoding**. When a format specifies UTF-8, process it as UTF-8 and manage BOMs strictly per that format's specification.

## 13. Do Not Confuse a BOM with Charset Trust for Unknown Sources

"Has a BOM" does not guarantee the following content is valid. "No BOM" is also not enough to conclude a file is ASCII or UTF-8.

Common sources of error:

- The application uses `Charset.defaultCharset()` instead of the protocol's charset.
- A file was written in Windows-1252 or a legacy code page, yet read as UTF-8.
- A BOM-less UTF-16LE file is read as UTF-8, producing interspersed NULs or unexpected characters.
- A UTF-8 BOM file is parsed as an ordinary CSV column name.
- A file has corrupted bytes or is truncated at the end, and a `REPLACE` decoder destroys evidence of the error.
- A network protocol specifies a length prefix in **bytes**, yet the writer sends `String.length()`.
- HTTP/content metadata and actual bytes disagree; the application must still follow the spec.

Never guess a charset from a few bytes for security-sensitive data or data requiring strict integrity. Without trusted metadata, establish an **explicit encoding contract/detection strategy** and validate at the business layer.

## 14. `CodingErrorAction`: `REPORT`, `REPLACE`, `IGNORE`

Java `CharsetDecoder` allows configuring:

```java
CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

This is an illustrative snippet requiring `CharsetDecoder`, `StandardCharsets`, and `CodingErrorAction`.

Comparison table:

| Policy | Behavior | When to Use |
|---|---|---|
| `REPORT` | Returns an error `CoderResult` / throws an exception when handled | Data requiring exact bytes, configs, protocols, testing |
| `REPLACE` | Inserts the decoder's replacement character | Best-effort display where data loss is acceptable |
| `IGNORE` | Drops invalid input | Only when business rules allow discarding data without breaking meaning |

### Malformed UTF-8

A byte sequence can be invalid because:

- A continuation byte appears without a preceding valid lead byte.
- A lead byte expects more continuation bytes, but an invalid byte follows.
- A sequence is cut off right at EOF.
- Bytes use an **overlong** encoding for a code point (forbidden by standard UTF-8).
- A sequence encodes surrogate code points or code points outside Unicode range.
- Bytes in another charset are mistakenly decoded as UTF-8.

Example of missing bytes:

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

This is an **illustrative code snippet** requiring imports for `ByteBuffer`, `CharsetDecoder`, `CodingErrorAction`, and `MalformedInputException`. The single-argument `decode(ByteBuffer)` overload performs a complete one-shot decode, so the incomplete 2-byte sequence is reported as malformed at the end of input. In streaming mode, calling `decode(input, output, false)` before EOF **waits** for the next byte instead of failing immediately.

### The Unicode Replacement Character Is More Than Cosmetic

If a program stores `�` into a file name, key, or signature instead of the original data, many things break:

- Byte hashes and checksums.
- User/resource name comparisons.
- JSON field names or CSV headers.
- Database queries and deduplication keys.
- Legal, financial, medical, or security-sensitive text.

Therefore, whenever accuracy matters, handle errors with `REPORT` or verify source encoding rather than turning corrupted input into "successfully decoded."

## 15. `ByteBuffer`: `flip`, `compact`, `clear`, and Boundary Bugs

`ByteBuffer` has three key state properties: `capacity`, `position`, and `limit`.

### After Reading Bytes from I/O

Buffer in write mode:

```text
capacity = 8
position = 5
limit = 8
[41 E2 98 95 42 | ...]
```

`flip()` sets `limit` to the current `position` and resets `position` to `0` so the decoder reads valid bytes:

```text
position = 0
limit = 5
[41 E2 98 95 42 | ...]
```

### When the Decoder Has Not Consumed All Bytes

Suppose the end of the buffer holds `E2 98`, missing byte `95`. After `decode`, `position` points at those two unconsumed bytes.

`compact()` keeps those two bytes, moves `position` to `2`, and resets `limit` to `capacity`. The next I/O read appends new bytes starting at index 2.

Calling `clear()` here **does not preserve undecoded bytes**, allowing old bytes to be overwritten; this is a common cause of `�` artifacts or flaky data loss that varies with buffer size.

### Decoder and `CharBuffer` Have Their Own Boundaries Too

When the output `CharBuffer` is too small, `decode` returns `OVERFLOW`. Drain the output and call `decode` again. Never interpret `OVERFLOW` as "compressed file too large" or "invalid UTF-8 bytes."

If the output `CharBuffer` has room for one UTF-16 unit, yet the next code point needs a two-unit surrogate pair, the decoder may return `OVERFLOW` rather than writing an invalid half-pair. Choose a buffer large enough to hold at least a surrogate pair and always handle `OVERFLOW`.

## 16. Self-Diagnosis via Hex Dump

When a character is corrupted, logging the `new String(...)` string can destroy evidence because invalid bytes were already replaced. Inspect the **raw bytes** in a test or safe environment:

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

This snippet requires importing `StandardCharsets` and can be placed in `main`. `StringBuilder.isEmpty()` is available on Java 17 (via `CharSequence`/`StringBuilder` depending on runtime); to avoid constraints on older environments, use `hex.length() > 0`.

Output:

```text
41 E2 98 95 42 F0 9F 98 80 43
```

**Never log raw bytes of passwords, access tokens, or personal data in production.** For real failures, prefer logging bounded metadata, offsets, expected charset, and byte samples redacted per policy.

### Diagnostic Information to Include

- Configured encoding/charset on both writer and reader.
- File path or source ID, file size, and byte offset where the error was detected.
- Individual chunk sizes and `ByteBuffer.position`/`limit`.
- Whether `CoderResult` was `UNDERFLOW`, `OVERFLOW`, or `MALFORMED`.
- Whether a BOM is present; whether it is at the start of the file or after another protocol prefix.
- The `REPORT`/`REPLACE`/`IGNORE` policy.
- Whether the data was gzipped/decompressed, decrypted, or transformed before decoding.
- Whether any code calls `new String(chunk)` with the default charset.
- Whether any logic blindly strips every `\uFEFF` or normalizes Unicode unchecked.

## 17. Diagnosing Byte Offsets vs. Char Indexes

If an error occurs at byte offset 127, you cannot infer that it corresponds to Java `String.charAt(127)` when the data is UTF-8.

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

For supplementary emojis, the divergence grows further because 4 UTF-8 bytes → 2 UTF-16 units → 1 code point.

When reporting parser errors, state explicitly whether the offset is:

- **Byte offset** in the file or wire stream.
- **UTF-16 char index** in a Java `String`.
- **Code point index** in the content.
- **Logical line/column** if the parser defines newline and Unicode rules.

If a binary protocol has a byte-length prefix, encode first to compute the length, and have the reader read all `length` bytes before decoding **only that payload**—never compute length with `String.length()`.

## 18. Byte Length in Network Protocols

Typical mistake:

```java
String body = "Cà phê ☕";
int declaredLength = body.length();   // Wrong if protocol requires byte count.
byte[] wire = body.getBytes(StandardCharsets.UTF_8);
```

If the protocol uses a frame `[4-byte payload length][payload bytes]`, the length must be `wire.length`, not `body.length()`.

Correct pattern (illustrative code):

```java
byte[] bodyBytes = body.getBytes(StandardCharsets.UTF_8);
if (bodyBytes.length > MAX_PAYLOAD_BYTES) {
    throw new IOException("Frame too large");
}
frame.putInt(bodyBytes.length);
frame.put(bodyBytes);
```

`body`, `MAX_PAYLOAD_BYTES`, and `frame` must be declared and allocated with enough capacity beforehand, and `frame` must use the `ByteOrder` agreed upon with the peer. On the reading side, use the exact advertised byte length, read the complete frame (handling partial I/O), and decode **after all bytes have arrived**. Even if a frame is split across TCP packets or file chunks, decoding has clear logical boundaries.

If the protocol uses a text delimiter such as newline, you must also define escaping, splitting `\r\n` across buffers, and line length limits. **Network I/O boundaries do not automatically become record boundaries or Unicode character boundaries.**

## 19. Unicode Normalization: Visually Identical Does Not Mean Byte-Equal

Two strings can render identically yet differ in Unicode encoding:

```java
String a = "\u00E9";
String b = "e\u0301";

System.out.println(a.equals(b)); // false

String na = Normalizer.normalize(a, Normalizer.Form.NFC);
String nb = Normalizer.normalize(b, Normalizer.Form.NFC);
System.out.println(na.equals(nb)); // true
```

This is an illustrative snippet requiring `java.text.Normalizer`, runnable inside a Java 17 method.

- **NFC** composes canonical equivalents per the Unicode standard.
- **NFD** decomposes into canonical decomposition.
- NFKC/NFKD apply compatibility mappings, which can alter the meaning or visual style of certain characters beyond canonical normalization.
- Never silently normalize fields such as identifiers, passwords, or signed strings unless the protocol specifies it.
- Do not treat normalization as a complete defense against homograph, spoofing, or confusable-character attacks.

To test Vietnamese data, include both precomposed forms and combining marks, verify byte round-trips when raw preservation is required, and test normalization separately according to business rules.

## 20. Minimum Test Cases for Streaming Unicode

A test suite should include the following strings and scenarios:

| Scenario | What It Proves |
|---|---|
| ASCII `Hello` | Baseline without multi-byte characters |
| Vietnamese `Cà phê` | Non-ASCII Unicode |
| `☕` split after byte 1 and byte 2 | Decoder retains 1–2 missing bytes |
| `😀` split after bytes 1, 2, and 3 | Decoder retains up to 3 leading bytes |
| UTF-8 BOM `EF BB BF` split into 3 chunks | BOM policy applies cleanly once |
| No BOM | Does not accidentally drop the first character |
| `U+FEFF` in the middle of content | Does not delete every `U+FEFF` |
| UTF-16BE/LE with BOM | Correct endianness per format |
| UTF-16LE without BOM | Decodes properly only when charset is known |
| UTF-8 input missing final byte | `REPORT` catches truncated input at EOF |
| Stray continuation byte `80` | Malformed input detected properly |
| Full output buffer | `OVERFLOW` is drained without losing characters |
| Decoder fed chunks of size 1, 2, 3, 4, 7... | Output is invariant across chunking strategies |
| Strings with combining accents | Does not confuse `equals` with canonical equivalence |
| Emoji with surrogate pair | Not split in half when processing Java `char[]` |
| Length-prefixed UTF-8 protocol | Length measured in bytes, not `String.length` |

### Property-Style Test: Invariance Across Chunk Boundaries

A strong rule:

> Given the same valid UTF-8 byte sequence, the output of a stateful decoder must be identical regardless of how the input is split into 1-, 2-, 3-, ... byte chunks (as long as byte order is preserved and EOF is signaled accurately).

You can write a test looping over different fixed chunk sizes, then add randomized partitioning tests. You do not need "one packet = one message" to decode text correctly.

Likewise, for invalid UTF-8 sequences, the **error policy** must be consistent: `REPORT` detects malformed/truncated input, while `REPLACE` produces output per the replacement policy; never silently accept invalid data simply because the split landed on a different boundary.

## 21. BOMs and Inputs with Binary Prefixes/Headers

In some protocols, a byte stream starts with a **binary header** followed by a text field. In that case, a BOM (if permitted by the spec) must be checked **at the start of the text field**, not necessarily at offset 0 of the entire stream.

Example:

```text
[magic: 4 bytes][version: 1][textLength: 4][text UTF-8 bytes]
```

If `text UTF-8 bytes` begins with `EF BB BF`, the BOM policy applies after the parser reads the header and locates the payload. If the parser wrapped the entire byte stream in `InputStreamReader` starting at byte 0, the binary header would be decoded as bogus characters and shift byte offsets.

Therefore:

1. Parse the **binary structure** in bytes first.
2. Locate the byte range of the text payload.
3. Determine the charset from the spec or metadata.
4. Apply the BOM policy at the **start of the payload**.
5. Decode the exact range with a stateful decoder, or read all bytes of the field and decode once.

Do not assume every `EF BB BF` appearing inside a payload is a BOM; it can also be an intentional `U+FEFF` character in the content.

## 22. When Is Independent Per-Chunk Decoding Valid?

Not every chunked decode is wrong. If **the protocol defines each chunk as an independent, self-contained UTF-8 string** with a clear length prefix and the sender guarantees never to split an encoding sequence, then decoding each message independently is valid.

Example:

```text
Frame 1: [length=3]["☕" UTF-8 3 bytes]
Frame 2: [length=4]["😀" UTF-8 4 bytes]
```

The reader must read all 3 or 4 bytes before creating the `String`. If the network layer splits a frame across multiple reads, accumulate **all frame bytes** first. The unit eligible for independent decoding is the **protocol-defined message boundary**, not an accidental socket or file buffer boundary.

Some text protocols like JSON Lines have explicit delimiters; the parser must detect delimiters according to the charset and enforce line length limits. In UTF-8 multi-byte characters, continuation bytes cannot be confused with an ASCII newline byte, though the parser must still ensure it does not confuse framing with another byte-order encoding.

## 23. Common Mistakes and Fixes

1. **`new String(buffer, 0, n, UTF_8)` on every read followed by concatenation.** Fails when a code point is split; use `InputStreamReader` or a stateful `CharsetDecoder`.
2. **Using `String.length()` as the byte count written on the wire.** Wrong for UTF-8; encode first and use `byte[].length`.
3. **Treating a Java `char` as a code point.** False for surrogate pairs; use `codePoints()` or appropriate `Character` APIs.
4. **Calling `ByteBuffer.clear()` when the decoder returns `UNDERFLOW` with incomplete bytes.** Discards bytes; use `compact()`.
5. **Forgetting `flip()` before decoding.** The decoder may read the wrong slice or nothing at all.
6. **Failing to drain `CharBuffer` after `OVERFLOW`.** The loop stalls or drops output.
7. **Calling `decode(..., true)` after every chunk.** When a chunk ends mid-code-point, the decoder assumes EOF and reports malformed input.
8. **Forgetting to call `flush` after `decode(..., true)`.** With stateful decoders, trailing output or finalization steps can be lost.
9. **Sharing one `CharsetDecoder` across multiple streams simultaneously.** Decoders hold state and must not be shared across streams or threads.
10. **Not calling `reset()` on a decoder before reusing it for a new independent stream.** State and decoding progress can become invalid.
11. **Treating `CodingErrorAction.REPLACE` as lossless data transmission.** Replacement loses information and must not be used when round-tripping is required.
12. **Ignoring malformed bytes (`IGNORE`) without evaluating business impact.** Can alter identifiers or headers.
13. **Assuming every Unicode file has a BOM.** UTF-8 BOMs are optional, and many formats forbid them.
14. **Deleting `U+FEFF` at every position.** If stripping is needed, remove it only at the beginning per spec.
15. **Confusing UTF-16BE and UTF-16LE BOMs.** Wrong endianness turns content into gibberish.
16. **Checking UTF-16 before UTF-32 when supporting both.** UTF-32LE BOM starts with `FF FE`, matching UTF-16LE; use a longest-match rule.
17. **Assuming raw UTF-8 bytes of NFC and NFD are identical.** They may render alike while differing in bytes and code points.
18. **Relying on decoded string logs to diagnose bad bytes.** Replacement hides original bytes; inspect safe hex dumps.
19. **Reading an entire untrusted file with `readAllBytes` before decoding.** Easily exhausts memory; use streaming with quotas.
20. **Assuming `InputStreamReader` returns intact grapheme clusters on every read.** It returns `char` units; downstream layers still must manage surrogates and graphemes when splitting `char[]`.
21. **Failing to check EOF at end of file.** Truncated UTF-8 only triggers an error once you know no more bytes will arrive.
22. **JSON/XML/CSV parsers not agreeing on charset between writer and reader.** Determine it from the spec, not random environment defaults.
23. **Normalizing all text without checking the contract.** Can break signatures, identifiers, or data requiring byte preservation.
24. **Guessing charset from the file extension.** File names do not guarantee content encoding.
25. **Assuming network reads match message boundaries.** TCP is a byte stream and requires explicit framing.

## 24. Practice Exercises

**Exercise 1 — Varying Chunk Sizes.** Modify `UnicodeBoundaryDemo` from 2 bytes per read to 1, 3, 4, and 5 bytes per read. Prove `Split-safe equals: true` in all runs when the file and charset are valid. Do not recreate the decoder inside the loop.

**Exercise 2 — Corrupting the Final Byte.** Take the UTF-8 bytes of `"😀"` and drop the last byte. Use `CharsetDecoder` with `REPORT`, call `decode(..., true)` at EOF, and confirm the malformed error. Then try `REPLACE` to observe that the output no longer matches the original.

**Exercise 3 — UTF-8 BOM Split Across Three Reads.** Write bytes `EF BB BF 41` and use an `InputStream` returning one byte at a time. Ensure the detector does not mistake a lone `EF` for a complete BOM, and that the post-policy output is `A`.

**Exercise 4 — UTF-16BE and UTF-16LE.** Generate byte sequences for `"A☕"` using `UTF_16BE` and `UTF_16LE`. Compare hex, decode with the right charset, then decode with the wrong one to observe the difference.

**Exercise 5 — Surrogate Pairs.** Read a Unicode emoji into a Java `char[]`. Split the `char[]` right between the high and low surrogates, then implement a code-point processor that retains the trailing high surrogate until the next read.

**Exercise 6 — Binary Length Prefix.** Implement a protocol `int32 byteLength + UTF-8 payload`. Send `"Cà phê ☕"`, split the payload across random read sizes, and verify the final `String` equals the original.

**Exercise 7 — Normalization.** Compare `"\u00E9"` and `"e\u0301"` on `equals`, code point count, UTF-8 bytes, and results after `Normalizer.Form.NFC`.

**Exercise 8 — Diagnostics.** When malformed UTF-8 is detected, log the expected charset, byte offset, and **redacted** hex bytes without logging full sensitive content. Write tests for bytes `80` and `E2 98`.

## 25. Self-Check Questions

**Q1.** Reading two bytes `E2 98` at the end of **a single read**—is that enough reason to report corrupted UTF-8?  
**No**, if the byte stream has not reached EOF. It may be the valid prefix of a three-byte code point. The decoder must wait for the next byte.

**Q2.** If **true EOF** is known and only `E2 98` remains, what is the result of strict decoding?  
**Malformed input**, because the sequence is incomplete.

**Q3.** Why can `new String(chunk1,UTF_8)+new String(chunk2,UTF_8)` fail?  
**Because each independent decoder** forgets the leading bytes of a code point that appeared in the previous chunk.

**Q4.** How does `ByteBuffer.compact()` help in an incremental decoder?  
**It preserves unconsumed bytes** while waiting for the next chunk and frees space at the end for appending.

**Q5.** Does `CoderResult.OVERFLOW` mean invalid UTF-8 data?  
**No.** It usually means the output `CharBuffer` ran out of space and must be drained before continuing decoding.

**Q6.** Does `"😀"` have `length() == 1`?  
**No**. `String.length() == 2` due to the UTF-16 surrogate pair, though it has 1 Unicode code point.

**Q7.** Which bytes make up the UTF-8 BOM?  
**EF BB BF**. UTF-8 does not need a BOM to determine endianness.

**Q8.** Does Java's UTF-8 decoder always strip a leading `EF BB BF` automatically?  
**No**. Many standard decoding APIs return it as character `U+FEFF`; an explicit policy is needed.

**Q9.** Should you call `text.replace("\uFEFF","")` to handle a BOM?  
**Not by default**, because it deletes `U+FEFF` everywhere. A BOM belongs only at the **start of a stream or field**, not every `U+FEFF` character.

**Q10.** A protocol sends a UTF-8 string with a byte-length prefix. Can you use `String.length()`?  
**No**; encode first and use the actual byte count.

**Q11.** Does `InputStreamReader` decoding UTF-8 across byte chunks automatically guarantee `read(char[])` calls never split a surrogate pair?  
**Do not rely on it**; the `char`-unit processing layer remains responsible for code point and grapheme boundaries.

**Q12.** Why is `REPORT` valuable when testing input data?  
**It surfaces encoding errors clearly**, instead of silently inserting replacements and treating corrupted data as valid.

**Q13.** Do two strings that look like `é` necessarily have the same UTF-8 bytes?  
**No**. One can be `U+00E9` while the other is `U+0065 U+0301`.

**Q14.** When supporting both UTF-16 and UTF-32 BOMs, why check the longest BOM first?  
**To avoid misreading the `FF FE` prefix of UTF-32LE** as a complete UTF-16LE BOM.

## 26. Implementation and Testing Checklist

- [ ] Determine the exact charset from the protocol or trusted metadata, preferring UTF-8 when the spec allows.
- [ ] Specify encoding explicitly on both writer and reader; never rely on the default charset.
- [ ] Distinguish byte offset, Java UTF-16 index, code point, and grapheme.
- [ ] Never decode individual byte chunks independently unless guaranteed to hold a complete message.
- [ ] For simple text streams, use `InputStreamReader`/`BufferedReader` with an explicit charset.
- [ ] For binary protocols/`ByteBuffer`, use a stateful `CharsetDecoder` and retain leftover bytes with `compact()`.
- [ ] Pass `decode(..., true)` **only at EOF**, then `flush` according to the protocol.
- [ ] Drain the output buffer on `OVERFLOW` without losing bytes or input state.
- [ ] Choose `REPORT` for data requiring exactness; log and handle errors explicitly.
- [ ] Enforce byte, character, CPU, and timeout limits appropriate to source trust.
- [ ] Define a BOM policy: allow, strip at start, or reject per format.
- [ ] For UTF-16, determine BE/LE; do not guess BOMs when the format fixes the charset.
- [ ] Do not blindly strip `U+FEFF` from the middle of content.
- [ ] For network framing, compute length in bytes after encoding.
- [ ] Test with Vietnamese text, emojis, combining marks, UTF-8 BOMs, and EOF mid-code-point.
- [ ] Test small chunk sizes: 1, 2, 3, 4, ... bytes and random splits.
- [ ] Verify byte round-trips when exact preservation is required.
- [ ] Apply normalization strictly per contract; never silently turn NFD into NFC when disallowed.
- [ ] Define behavior for malformed bytes and wrong encodings.
- [ ] Never log raw sensitive data in diagnostic messages.

## 27. Summary

- **Unicode is a set of code points; UTF-8/UTF-16 are ways of encoding them into storage/transmission units.**
- **One byte read does not equal one Unicode character.** UTF-8 uses 1–4 bytes per code point, so sequences must be allowed to span chunks.
- **Never call `new String` independently on arbitrary chunks.** Use `InputStreamReader` or a stateful `CharsetDecoder`.
- **`flip()` switches to reading; `compact()` retains incomplete bytes; `clear()` can discard them.**
- **Signal EOF only when the stream ends**, execute final decode + `flush`, and report malformed input when truncated.
- **The UTF-8 BOM is `EF BB BF`**, optional; UTF-16 BOMs indicate endianness. BOM policy must follow the format and apply only at the start of a stream or payload.
- **Byte count ≠ `String.length()` ≠ code point count**, especially with Vietnamese text, emojis, and combining marks.
- **Boundary testing and error-policy testing are mandatory** so corrupted data is never silently turned into replacement characters unnoticed.

### Java SE 17 API Documentation

- [CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [CoderResult](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CoderResult.html)
- [CodingErrorAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [InputStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html)
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
