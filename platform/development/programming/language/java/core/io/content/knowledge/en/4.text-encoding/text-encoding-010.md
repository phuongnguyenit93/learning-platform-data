# Multi-Chunk Decoding When a Character Splits Across Two Reads in Java I/O

## 1. The Problem: Byte Chunk Boundaries Are Not Character Boundaries

When reading text from a file, socket, or an `InputStream`, data arrives as **bytes**. A single `read(byte[])` call returns only one chunk of bytes available at that moment; that chunk does not necessarily end cleanly at the end of an encoded character. For example, in UTF-8, one Unicode character can be encoded into **1–4 bytes**. If a read stops in the middle of a character's bytes, decoding each chunk independently can produce replacement characters `�` or spurious errors.

Example of `€` (U+20AC) in UTF-8:

~~~text
Original text:             €
UTF-8 bytes (hex):         E2 82 AC

Read 1:                    E2 82       ← not yet a complete character
Read 2:                          AC    ← completes the character

Correct: keep E2 82, append AC, decode → €
Wrong:   decode E2 82 separately, then AC separately → string is no longer €
~~~

A similar case: the emoji `😀` (U+1F600) has UTF-8 sequence `F0 9F 98 80`. Any read boundary falling anywhere inside these four bytes requires preserving decoder state. In Java, that emoji is also represented as **two `char` units (a surrogate pair)** after decoding into UTF-16.

This lesson focuses on **incremental decoding**: processing multiple consecutive byte chunks as **one continuous text stream**, retaining incomplete data between reads, recognizing true EOF, and signaling errors accurately.

Target outcomes:

- Explain why you should not construct a separate `new String(chunk, charset)` for each byte chunk of the same data stream.
- Understand how `InputStreamReader` retains state to help applications read ordinary characters.
- Use `CharsetDecoder` directly with `ByteBuffer` and `CharBuffer` when you need control over multi-chunk decoding.
- Distinguish `CoderResult.UNDERFLOW`, `OVERFLOW`, malformed input, and EOF; set `endOfInput` and call `flush()` at the right lifecycle points.
- Test arbitrary byte boundaries, including splits across Vietnamese characters and emojis.

## 2. Three Data Layers: Bytes, Code Points, and `char`

Before writing a loop, separate three concepts:

| Concept | Example | Role |
| --- | --- | --- |
| Byte | `E2`, `82`, `AC` | Raw data unit transmitted by file or network I/O |
| Unicode code point | `U+20AC` for `€` | Abstract value representing one Unicode character |
| UTF-16 code unit (`char`) | `'\u20AC'` or one half of a surrogate pair | How many Java character APIs represent text |

In UTF-8, ASCII like `A` uses 1 byte; `€` uses 3 bytes; `😀` uses 4 bytes. After decoding, `€` is one `char`, while `😀` requires two `char`s. Therefore:

- **The number of bytes read does not equal the number of Java characters received.**
- **The number of `char`s does not always equal the number of code points.**
- **The byte count of one read does not dictate how many characters can be emitted immediately.**

A decoder waiting for the final byte of a character may **emit zero `char`s**, even though the application just fed it more bytes. This is normal; do not insert empty or replacement characters merely because the current chunk produced no output yet.

## 3. Why Decoding Each Byte Array with `new String` Is Wrong

The following snippet illustrates a common bug:

~~~java
StringBuilder result = new StringBuilder();
byte[] buffer = new byte[2];
int count;

while ((count = input.read(buffer)) != -1) {
    result.append(new String(buffer, 0, count, StandardCharsets.UTF_8));
}
~~~

**This is a non-standalone illustrative snippet:** `input` is an already-opened `InputStream`; matching imports and closing by the stream owner are required. The bug is that **each call to the `String` constructor starts an independent decoding session**. If UTF-8 data is split across two `read` calls, the previous decoder no longer has any chance to receive the subsequent bytes.

More concretely, consider a string containing only `€` split into two arrays: `{E2, 82}` and `{AC}`. Because each piece on its own is an invalid UTF-8 sequence, the `new String(byte[], UTF_8)` API applies a **replace invalid data** policy instead of joining the two parts into `€`. The fact that each piece decodes without throwing an exception does not prove the text is intact.

Do not “solve” this by picking a 4096- or 8192-byte buffer: a larger buffer **reduces the probability** of hitting a split character on typical data, yet does not eliminate it. Any finite chunk size can still cut right through a multi-byte UTF-8 sequence.

There are two right approaches:

1. **Use a `Reader` class to read decoded characters**: suitable for most programs that simply need text.
2. **Keep one `CharsetDecoder` across the entire data stream**: suitable when managing `ByteBuffer`/`CharBuffer` directly, performing asynchronous reads, framing messages, or needing an explicit error-reporting policy.

## 4. The Simple Approach: Let `InputStreamReader` Hold Decoder State

`InputStreamReader` bridges `InputStream` (bytes) and `Reader` (characters). It preserves decoding state across multiple underlying byte reads. Callers receive `char` units only once the library has enough bytes.

~~~java
try (Reader reader = new InputStreamReader(
        input, StandardCharsets.UTF_8)) {
    char[] chars = new char[1024];
    int count;

    while ((count = reader.read(chars)) != -1) {
        // Process exactly chars[0] through chars[count - 1].
    }
}
~~~

This snippet requires `import java.io.Reader`, `import java.io.InputStreamReader`, and `import java.nio.charset.StandardCharsets`, along with a supplied `InputStream input`. `try-with-resources` closes the `Reader` and thus closes the underlying `InputStream`; use it only when this code **owns** the `InputStream` or is authorized to close it.

Although `Reader` solves UTF-8 splits across byte reads, `Reader` itself can still return `char[]` chunks split between the **two surrogate units** of a Unicode code point. If you only write each chunk verbatim with `Writer.write(chars, 0, count)` in the same text stream, that works fine; if you treat each chunk as an independent character string to reverse, filter, or analyze code points, you must account for UTF-16 boundaries.

### 4.1. Standalone runnable example with a byte-by-byte source

File **ReaderAcrossChunksDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;

public class ReaderAcrossChunksDemo {
    public static void main(String[] args) throws Exception {
        String original = "A€😀B";
        byte[] bytes = original.getBytes(StandardCharsets.UTF_8);

        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes), StandardCharsets.UTF_8)) {
            StringBuilder restored = new StringBuilder();
            char[] buffer = new char[2];
            int count;

            while ((count = reader.read(buffer)) != -1) {
                restored.append(buffer, 0, count);
            }

            System.out.println("UTF-8 bytes: " + bytes.length);
            System.out.println("UTF-16 units: " + restored.length());
            System.out.println("Restored: " + restored);
            System.out.println("Matches: " + original.contentEquals(restored));
        }
    }
}
~~~

Run with Java 17+:

~~~bash
javac -encoding UTF-8 ReaderAcrossChunksDemo.java
java ReaderAcrossChunksDemo
~~~

Output:

~~~text
UTF-8 bytes: 9
UTF-16 units: 5
Restored: A€😀B
Matches: true
~~~

`ByteArrayInputStream` in the example already holds all bytes in RAM; `Reader` may gather bytes internally as needed, so each `read(char[])` call need not correspond to individual byte chunks. Still, the output demonstrates the crucial rule: **through the same `Reader`, UTF-8 data is decoded continuously without creating a new decoder per read**.

When you must observe or explicitly feed **exact byte fragments**, you need the `CharsetDecoder` example in the next sections.

## 5. `CharsetDecoder`: Where Is Decoding State Held?

`java.nio.charset.CharsetDecoder` is a stateful object used to convert bytes into Java UTF-16 units. Create one single decoder for **one continuous data stream**:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

Required imports: `java.nio.charset.CharsetDecoder`, `CodingErrorAction`, and `StandardCharsets`. This is an illustrative snippet, not a standalone program.

When processing input across multiple chunks, the key objects are:

- `ByteBuffer input`: holds currently available bytes, **including any partial sequence not yet sufficient to form a character**.
- `CharBuffer output`: where the decoder writes decoded `char` units.
- `CharsetDecoder decoder`: holds the decoding process state, including charset rules and end-of-stream state.
- `CoderResult result`: reports the decoder's status after a pass.

With `CharsetDecoder.decode(input, output, endOfInput)`:

| Result | Meaning | How to Handle |
| --- | --- | --- |
| `UNDERFLOW` | Cannot produce further output from the available bytes; either more bytes are needed to finish a character or all input was consumed | Keep remaining bytes, feed more; if at end of stream, prepare to flush |
| `OVERFLOW` | `CharBuffer` lacks enough space to emit more output | Pass produced characters to consumer, clear `CharBuffer`, then call decode again |
| `isMalformed()` | Byte sequence is invalid under the charset | Handle per error policy; if `REPORT`, throw exception |
| `isUnmappable()` | Data cannot be mapped to output in the charset | Handle per error policy; do not assume EOF |

**Note:** `UNDERFLOW` does not necessarily mean “all data is exhausted.” When `endOfInput=false`, it may simply indicate the decoder needs the next bytes. Do not terminate processing of the entire source whenever you see `UNDERFLOW`.

### 5.1. Choosing an error policy

There are three typical choices for invalid byte sequences:

- `CodingErrorAction.REPORT`: lets `CoderResult` report an error (or throws `CharacterCodingException` via `throwException()`). Suitable when data requires strict accuracy.
- `CodingErrorAction.REPLACE`: uses the decoder-defined replacement string (commonly `�` for UTF-8). Suitable when displaying recoverable data takes priority.
- `CodingErrorAction.IGNORE`: drops invalid data. Risks silent data loss; use only when business logic permits.

**Bytes split across two reads are not an error.** When the decoder receives `endOfInput=false`, the incomplete byte portion must be retained to try with subsequent bytes. Only when the stream truly ends while required bytes are still missing does a truncated sequence become invalid input under the charset contract.

## 6. `ByteBuffer` Lifecycle: `position`, `limit`, `flip`, and `compact`

`ByteBuffer` has three primary indices:

- `capacity`: total size of the container.
- `position`: index of the next read/write.
- `limit`: current boundary that operations must not cross.

When **writing bytes into the buffer**, the buffer is usually in write mode: `position` advances after `put`, and `limit` usually equals `capacity`. Before the decoder **reads from the buffer**, call `flip()` to set `limit = position` and `position = 0`.

~~~text
ByteBuffer in read mode:

[ E2 ][ 82 ][  · ][  · ][  · ][  · ]
  ^position      ^limit          ^capacity
  Bytes E2 82 are not enough to form €

Decoder returns UNDERFLOW; position still points to the unconsumed bytes.
Call compact():
- moves remaining bytes to the start of the array
- sets position after the remaining bytes
- sets limit to capacity to make room for more input

Load AC, call flip():

[ E2 ][ 82 ][ AC ][  · ][  · ][  · ]
  ^position            ^limit

Decoder continues → €
~~~

In a correct algorithm, **`compact()` is critical**: it preserves bytes the decoder has not yet consumed. Calling `clear()` after `UNDERFLOW` would discard the partial bytes of the character; when the next bytes arrive, the remainder can no longer join with the earlier part.

Core differences:

| Operation | Effect | When to Use |
| --- | --- | --- |
| `flip()` | Turns newly written data into a readable region | After loading more bytes before decoding |
| `compact()` | Keeps **unread** data at the start of the buffer and opens space for new writes | After a decode pass before loading the next bytes |
| `clear()` | Sets `position=0`, `limit=capacity` without erasing physical contents | Only when certain no old bytes need preserving |
| `remaining()` | Returns number of elements between `position` and `limit` | To know how many bytes remain to read/write |
| `hasRemaining()` | Checks whether any elements remain | Controls loops; does not by itself signify source EOF |

`CharBuffer` also has `position`/`limit`. After each `decode`, to deliver produced characters to the consumer: call `output.flip()`, read all remaining characters, then call `output.clear()` so the decoder can produce more. **Never call `output.clear()` before draining decoded data.**

## 7. Incremental Decoding Algorithm

A standard loop for a continuous byte stream consists of these steps:

1. Create **one** `CharsetDecoder` and configure its error policy.
2. Allocate a `ByteBuffer` large enough to hold the charset's maximum byte sequence plus room to load more; allocate a `CharBuffer` large enough for the output a decoder can emit for a single character.
3. Read a batch of bytes from the source and put them into `ByteBuffer`. Use `compact()` before loading to retain unconsumed bytes; use `flip()` so the decoder sees all valid bytes.
4. Call `decode(input, output, false)` while **more bytes may still arrive** from the source. On `OVERFLOW`, drain output and call again. On `UNDERFLOW`, keep leftover bytes and wait for the next chunk.
5. Once **true source EOF is confirmed**, call `decode(input, output, true)` with the remaining bytes (which may be empty). At this point, leftover bytes failing to form a valid character are handled as truncated trailing data per the error policy.
6. After the final decode returns `UNDERFLOW`, call `decoder.flush(output)`; handle `OVERFLOW` by draining output and calling flush again until `UNDERFLOW`.
7. Call `decoder.reset()` only if reusing the decoder for **another independent stream**, after the current lifecycle has ended properly. Never reset between chunks of the same source.

This is a **state machine**. Calling `flush()` before `decode(..., true)` finishes or feeding more bytes to a finished decoder without resetting violates state order. A `CharsetDecoder` must not be treated as safe for concurrent manipulation by multiple threads sharing state; each independent decoding stream should own its own decoder or synchronize by design.

### 7.1. Note on an overly small `ByteBuffer`

If the input buffer is too small to hold a byte sequence required for the decoder to advance, the loop can stall: `UNDERFLOW` retains all bytes, leaving `compact()` with zero space to load more. For UTF-8, one code point needs at most 4 bytes; the example below uses an 8-byte buffer. When designing a general decoder for other charsets, ensure adequate buffer capacity or a growth mechanism.

Similarly, `CharBuffer` must have enough room for one output unit the decoder must emit at once; an emoji outside the BMP can require two `char` units. The example uses `CharBuffer.allocate(2)`. If `CharBuffer` has capacity 1 and the decoder needs to emit a surrogate pair together, a naive loop can keep hitting `OVERFLOW` without making progress.

## 8. Complete Java 17 Example: Intentionally Splitting UTF-8 into 2-Byte Chunks

The example below feeds two bytes per pass, splitting `€` (3 bytes) and `😀` (4 bytes) across passes. The result must match the original string **exactly**. The example handles `UNDERFLOW`, `OVERFLOW`, `ByteBuffer` leftovers, and final flush.

Save to **Utf8IncrementalDecoderDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class Utf8IncrementalDecoderDemo {
    public static void main(String[] args) throws Exception {
        String original = "A€😀B";
        byte[] bytes = original.getBytes(StandardCharsets.UTF_8);
        String decoded = decodeInChunks(bytes, 2);

        System.out.println("UTF-8 bytes: " + bytes.length);
        System.out.println("UTF-16 units: " + decoded.length());
        System.out.println("Decoded: " + decoded);
        System.out.println("Matches: " + original.equals(decoded));
    }

    static String decodeInChunks(byte[] bytes, int chunkSize)
            throws CharacterCodingException {
        if (chunkSize <= 0) {
            throw new IllegalArgumentException("chunkSize must be positive");
        }

        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        ByteBuffer input = ByteBuffer.allocate(8);
        CharBuffer output = CharBuffer.allocate(2);
        StringBuilder result = new StringBuilder();

        // Read mode with zero bytes waiting.
        input.limit(0);
        int next = 0;

        while (next < bytes.length) {
            // Keep unconsumed bytes, making room for new data.
            input.compact();
            int count = Math.min(
                    chunkSize, Math.min(input.remaining(), bytes.length - next));
            if (count == 0) {
                throw new IllegalStateException("Input buffer too small");
            }

            input.put(bytes, next, count);
            next += count;
            input.flip();

            boolean endOfInput = next == bytes.length;
            decodeAvailable(decoder, input, output, result, endOfInput);
        }

        // Empty input case still requires terminating the decoder.
        if (bytes.length == 0) {
            decodeAvailable(decoder, input, output, result, true);
        }

        // Flush only after the final decode returns UNDERFLOW.
        while (true) {
            CoderResult status = decoder.flush(output);
            drain(output, result);

            if (status.isOverflow()) {
                continue;
            }
            if (status.isError()) {
                status.throwException();
            }
            if (status.isUnderflow()) {
                break;
            }
        }

        return result.toString();
    }

    private static void decodeAvailable(
            CharsetDecoder decoder, ByteBuffer input, CharBuffer output,
            StringBuilder result, boolean endOfInput)
            throws CharacterCodingException {
        while (true) {
            CoderResult status = decoder.decode(input, output, endOfInput);
            drain(output, result);

            if (status.isOverflow()) {
                // CharBuffer was drained and cleared: retry decoding.
                continue;
            }
            if (status.isError()) {
                status.throwException();
            }
            if (status.isUnderflow()) {
                // ByteBuffer may still hold the start of an incomplete character.
                break;
            }
        }
    }

    private static void drain(CharBuffer output, StringBuilder result) {
        output.flip();
        result.append(output);
        output.clear();
    }
}
~~~

Compile and run (JDK 17+):

~~~bash
javac -encoding UTF-8 Utf8IncrementalDecoderDemo.java
java Utf8IncrementalDecoderDemo
~~~

Expected output:

~~~text
UTF-8 bytes: 9
UTF-16 units: 5
Decoded: A€😀B
Matches: true
~~~

**Key points in the example:**

- `bytes.length == 9` because `A` takes 1 byte, `€` takes 3, `😀` takes 4, and `B` takes 1.
- `decodeInChunks(bytes, 2)` intentionally feeds 2 bytes per pass (the last pass may be shorter). Some passes deliver only the **leading or trailing fragment of the same character**.
- `input.compact()` moves undecoded bytes to the start of the buffer; `input.put` loads the next slice from the source; `input.flip()` prepares for the decoder.
- `decodeAvailable` handles `OVERFLOW` and drains characters from `CharBuffer` continuously. On `UNDERFLOW` before stream end, it yields control to load more bytes.
- `endOfInput` becomes `true` only after **the last byte of the source has been supplied**. Never infer EOF from a single `UNDERFLOW`.
- `decoder.flush(output)` runs after the final decode, ensuring all trailing state is processed.
- `StringBuilder.append(output)` extracts remaining characters in `CharBuffer` after `flip()`; `clear()` prepares space for fresh output.

This example teaches the mechanism. In real production code, combine byte loading from `InputStream`/`ReadableByteChannel`, I/O exception handling, cancellation, and resource lifecycles. A byte source can end with `-1` (EOF), whereas `0` when reading a non-blocking channel may simply mean no bytes are ready yet. Those two states **must never be equated**.

## 9. When Bytes Come from an Actual `InputStream` or Channel

### 9.1. `InputStream.read(byte[])`

For `InputStream`, the return value of `read(buffer)` is:

- The actual number of bytes read.
- `-1` when data is exhausted.
- With a zero-length array, the call may return `0`; never use an empty array as a loop buffer.

Example reading bytes from a file incrementally, which you can then feed into **the same decoder** or simply wrap with `InputStreamReader`:

~~~java
try (var input = java.nio.file.Files.newInputStream(path);
     var reader = new java.io.InputStreamReader(
             input, java.nio.charset.StandardCharsets.UTF_8)) {
    char[] buffer = new char[2048];
    int count;
    while ((count = reader.read(buffer)) != -1) {
        // Process each chunk of decoded characters.
    }
}
~~~

This snippet needs `Path path` and a method declaring or catching `IOException`. It shows `Reader` retaining state even as the underlying `InputStream` reads bytes over multiple calls; it is not a standalone program.

### 9.2. `ReadableByteChannel` and non-blocking I/O

A non-blocking channel can return `0` when **no bytes are available yet**, even while the connection remains open. In that case:

- Do not call `decode(..., true)`.
- Do not call `flush()` to “grab remaining characters.”
- Retain remaining bytes and decoder state, and wait for the next read.
- Signal `endOfInput=true` only when the protocol/API confirms the data to be decoded has truly ended.

With protocols where each message has its own length, the end of one message is not automatically EOF for **the entire connection**. You must decide whether the decoder continues over the same character stream or each message is an independent byte sequence (using a separate decoder or resetting at the right moment). Never treat “one `socket.read`” as a character boundary or message boundary.

## 10. Distinguishing `UNDERFLOW`, `OVERFLOW`, and Errors: Two Contrasting Cases

**Case A — Valid UTF-8 split across multiple chunks:**

~~~text
Byte stream:     E2 82 AC
Chunk 1:         E2 82
decode(false):   UNDERFLOW; no € character yet
Keep bytes:      E2 82
Chunk 2:         AC
decode(true):    produces €; then UNDERFLOW
flush():         UNDERFLOW, complete
~~~

This is the right outcome. Incomplete data in the first chunk **is not malformed**.

**Case B — Truly truncated UTF-8 at the end of the source:**

~~~text
Byte stream:     E2 82
Chunk 1:         E2 82
decode(false):   UNDERFLOW; waiting for next byte
Source truly ends:
decode(true):    MALFORMED (when policy is REPORT)
~~~

To reject invalid data, call `status.throwException()` to throw `MalformedInputException` (a kind of `CharacterCodingException`). If configured with `REPLACE`, the decoder may emit a replacement character instead of stopping; the application must choose the appropriate policy.

**Case C — Output buffer cannot hold enough:**

~~~text
Enough bytes read; decoder wants to emit more characters
CharBuffer is full or lacks sufficient space
decode(...):     OVERFLOW
Read all available characters from CharBuffer, then clear()
decode(...):     continue processing ByteBuffer at remaining position
~~~

`OVERFLOW` **does not mean the data is bad**; it reports insufficient output space. Conversely, calling `decode` repeatedly with the same full `CharBuffer` without draining data can loop forever without progress.

## 11. Do Not Reset the Decoder Between Chunks

A common mistake is writing:

~~~java
for (byte[] chunk : chunks) {
    CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder();
    // Decode each chunk separately...
}
~~~

The snippet above only illustrates the wrong idea: `chunks` is assumed to exist, and the code is not standalone. Each new decoder starts in its initial state, so the next chunk knows nothing about incomplete bytes from the previous chunk. Even keeping the same decoder while calling `reset()` after every pass destroys the state of a continuous data stream.

The right approach is creating one decoder for **the entire source**, keeping unconsumed `ByteBuffer` bytes and decoder state across passes. Call `reset()` only after the current lifecycle completes and when starting a new, encoding-independent source. With stateful encodings, preserving state is even more vital; you cannot force the mindset “each byte uniquely determines its own interpretation” onto every charset.

## 12. Data Errors, Quality Checks, and Recovery Strategies

An application importing config files or contract data typically requires precision: use `REPORT` to detect invalid or truncated byte sequences. A log viewer may prefer continuing: `REPLACE` makes sense if data loss is acceptable and surfaced clearly.

You can test error handling without creating files:

~~~java
byte[] incomplete = {(byte) 0xE2, (byte) 0x82};
// Decode using UTF-8 decoder with REPORT.
// With endOfInput=false: must wait for the next byte.
// With endOfInput=true: reports malformed.
~~~

This is an illustrative data snippet; to test invalid input, use the `decode` loop from the complete example and pass `incomplete`. `CharsetDecoder` can return an error `CoderResult`, and `throwException()` throws an exception; do not catch the error and manually write `"?"` if exact text preservation is required.

**You cannot fix data loss by concatenating Strings from broken decodes.** Once each segment has turned invalid bytes into `�`, original byte information may already be lost; keep the original bytes or re-decode the whole stream from the authoritative source.

If protocol-level recovery is needed, clarify whether the partial byte tail is:

- A character waiting for its next byte (not yet EOF).
- A genuinely corrupted/missing byte sequence.
- A chunk cut off due to a message boundary; you must specify whether decoding may continue into the next message.
- Valid UTF-8 data processed with the wrong charset.

These cases share the symptom “failed to produce a character yet,” while their fixes differ.

## 13. Notes on BOM, Charsets, and Per-Stream Encoding

UTF-8 does not require a Byte Order Mark (BOM), yet a source may begin with the three bytes `EF BB BF`. If decoded as ordinary content, a UTF-8 decoder may emit `U+FEFF`. Whether this leading character is a marker to strip or data to preserve **depends on the format and input contract**.

If a BOM is split across multiple reads, it must likewise be handled as a continuous byte sequence—never decode each piece separately. Do not blindly strip every `U+FEFF` appearing in text, as that can alter valid content.

For UTF-16 and other charsets, byte-order and state rules can differ from UTF-8. Pick the exact `Charset` up front, while keeping **the same decoder** for the entire data stream. Never switch charsets mid-stream just because one chunk did not yet decode into text.

## 14. Boundary Testing: Same Data, Every Chunk Split Must Pass

A thorough test does not only use large buffers. Take the same text string containing ASCII, accented letters, three-byte characters, and four-byte emojis, and feed it in chunk sizes of 1, 2, 3, 4, 5... bytes. For valid UTF-8 data, **the final decoded result must be identical**.

Example you can append right inside `main` of `Utf8IncrementalDecoderDemo` once `bytes` and `original` exist:

~~~java
for (int size = 1; size <= 9; size++) {
    String actual = decodeInChunks(bytes, size);
    if (!original.equals(actual)) {
        throw new AssertionError("Incorrect chunk size: " + size);
    }
}
System.out.println("All chunk sizes passed");
~~~

This is an **insertion snippet for the example class in section 8**, not a standalone program. If inserted after the existing print statements and re-run, the program additionally prints:

~~~text
All chunk sizes passed
~~~

Testing value:

- Size 1 forces every byte of `€` and `😀` across multiple chunks one by one.
- Sizes 2 and 3 produce varied split positions inside characters.
- Sizes 4 and up remain worth testing when characters appear in different orders.
- Test an empty `byte[]` to verify the decoder still terminates and flushes cleanly without error.
- Test truncated trailing bytes to verify `REPORT` detects malformed input instead of silently dropping data.

These tests catch common mistakes in calling `compact()`, setting `endOfInput` prematurely, forgetting to drain `CharBuffer`, resetting the decoder between passes, or inadvertently inserting replacement characters.

## 15. Common Implementation Mistakes

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| `new String(chunk, UTF_8)` per read then concatenating | A split multi-byte code point turns into `�` or corrupted text | `InputStreamReader` or one `CharsetDecoder` throughout |
| `ByteBuffer.clear()` after `UNDERFLOW` with leftover bytes | Discards incomplete leading bytes of a character | `compact()` to preserve unconsumed bytes |
| Setting `endOfInput=true` after every chunk | Decoder treats chunk end as stream end, falsely reporting malformed | Set `true` only at real EOF |
| Not calling `decode(..., true)` at EOF | Decoder never receives end signal to handle trailing remainder | Perform final decode pass |
| Not calling `flush()` after final decode | Stateful decoders may omit trailing output | Flush until `UNDERFLOW` |
| Hitting `OVERFLOW` without draining `CharBuffer` | Loop makes no progress and can hang | Flip → read output → clear → continue decoding |
| Discarding `input.remaining()` after `UNDERFLOW` | Loses data waiting for next bytes | Preserve unconsumed remainder |
| Creating an input buffer that is too small | Lacks space to assemble a multi-byte sequence | Allocate adequate buffer or grow on demand |
| Creating an output buffer that is too small | Lacks space to emit a surrogate pair | Allocate enough room for minimum output unit |
| Resetting the decoder after every pass | Wipes stream state | Reset only before a fresh independent stream |
| Equating `read() == 0` with EOF | Premature termination on non-blocking channels | Distinguish “no data yet” from `-1` |
| Not choosing a charset explicitly | Same bytes get interpreted differently | Specify charset per input format |
| Swallowing `CharacterCodingException` | Masks corrupted source data or misconfiguration | Report errors or apply explicit replacement policy |
| Counting characters by byte count | Wrong length for Vietnamese/emojis | Distinguish UTF-8 bytes, UTF-16 units, and code points |

## 16. Self-Check Questions

**Question 1.** A byte stream delivers `E2 82`, and the UTF-8 decoder with `endOfInput=false` returns `UNDERFLOW`. Is this corrupted data?

**Answer:** Not yet. The decoder lacks the third byte of a three-byte UTF-8 sequence; keep `E2 82` and feed `AC` next to obtain `€`.

**Question 2.** EOF is confirmed, and the decoder receives `E2 82` with `endOfInput=true` in `REPORT` mode. Should it wait further?

**Answer:** No. At genuine EOF, the data is truncated; report a malformed error via `CoderResult`/`CharacterCodingException`. Wait further only if the protocol has not actually ended.

**Question 3.** The decoder returns `OVERFLOW`. Should you immediately load more bytes into `ByteBuffer`?

**Answer:** No need. First drain `CharBuffer` and continue decoding the bytes already present; `OVERFLOW` concerns **output space**, not missing input bytes.

**Question 4.** Why does a `String` displaying an emoji have `length() == 2` even though the emoji is one code point?

**Answer:** `String.length()` counts UTF-16 code units. A code point outside the BMP uses a surrogate pair of two `char` units.

**Question 5.** When should you choose `InputStreamReader` over calling `CharsetDecoder` directly?

**Answer:** When the goal is simply sequential text reading and you do not need manual control over byte arrays, decoder state, or `CoderResult`. `InputStreamReader` handles bytes split across underlying reads.

**Question 6.** A non-blocking channel returns `0` bytes. Should you call `decode(input, output, true)`?

**Answer:** Not just because of a `0` return. This typically means no bytes are ready yet; wait further or track status per the protocol API. Mark EOF only when the source truly finishes.

## 17. Key Takeaways to Apply

1. **A text source is a continuous byte stream.** `read` boundaries carry no encoding meaning; one UTF-8 character can span multiple chunks.
2. **Decode statefully.** Simplest is one `InputStreamReader` for the whole source; when using NIO directly, keep one `CharsetDecoder` throughout.
3. **`UNDERFLOW` needs more data or finished available input; `OVERFLOW` needs output buffer space.** Neither is an error by itself.
4. **Preserve unconsumed bytes with `ByteBuffer.compact()`**, load more, then `flip()`. For `CharBuffer`, `flip()` to read characters and `clear()` once drained.
5. **Call `decode(..., true)` only at true EOF**, then `flush()` until `UNDERFLOW`. Do not reset between chunks, and do not close the stream merely because a single read ended.
6. **Test with 1–4 byte chunks, accented data, and emojis.** Test truncated data under `REPORT` policy to ensure errors are detected rather than producing garbled text.

### API Reference Documentation

- [CharsetDecoder — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [CoderResult — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CoderResult.html)
- [CodingErrorAction — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [ByteBuffer — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [InputStreamReader — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html)
- [StandardCharsets — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)