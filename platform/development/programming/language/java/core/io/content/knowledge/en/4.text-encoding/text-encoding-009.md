# CharsetEncoder, CharsetDecoder, and CodingErrorAction in Java

When Java works with files, HTTP, sockets, or text formats, the system must convert between **Unicode characters** and **bytes**. `CharsetEncoder` converts characters to bytes; `CharsetDecoder` converts bytes back to characters; `CodingErrorAction` specifies what to do when input is invalid or unrepresentable in the target charset.

This is part of **Text Encoding** in Java Core I/O, focusing on `java.nio.charset` and combining encoders/decoders with `ByteBuffer`, `CharBuffer`, `Reader`, and `Writer`. Examples use Java 17+.

## 1. Three Components Solving Three Different Problems

```text
Java String / char[] / CharBuffer
        |
        | CharsetEncoder (e.g., UTF-8)
        v
  ByteBuffer: encoded bytes
        |
        | file, network, device, memory
        v
  ByteBuffer: received bytes
        |
        | CharsetDecoder (same charset)
        v
Java String / char[] / CharBuffer

CodingErrorAction:
  REPORT   → report encoding/decoding error
  REPLACE  → replace invalid segment with replacement value
  IGNORE   → drop invalid segment
```

Key APIs:

| Component | Conversion Direction | Input → output | Common Initialization |
| --- | --- | --- | --- |
| `Charset` | Defines character ↔ byte mapping | Not a standalone process | `StandardCharsets.UTF_8` |
| `CharsetEncoder` | Encoding | `CharBuffer` → `ByteBuffer` | `charset.newEncoder()` |
| `CharsetDecoder` | Decoding | `ByteBuffer` → `CharBuffer` | `charset.newDecoder()` |
| `CodingErrorAction` | Error policy | `REPORT`, `REPLACE`, `IGNORE` | `onMalformedInput(...)` / `onUnmappableCharacter(...)` |
| `CoderResult` | Status of one incremental pass | `UNDERFLOW`, `OVERFLOW`, or error result | Result of `encode(..., ..., ...)` / `decode(..., ..., ...)` |

A simple example: `é` is one Unicode code point and usually takes one Java `char` unit, yet in UTF-8 it encodes into **two bytes** `C3 A9`. The emoji `😀` occupies two Java `char` units (a surrogate pair) and four UTF-8 bytes `F0 9F 98 80`. Therefore:

- `String.length()` counts **UTF-16 code units**, not output bytes.
- `CharBuffer` operates on `char` units and does not guarantee each element is a complete Unicode code point.
- `ByteBuffer` operates on bytes. Network send/receive boundaries can split across the byte sequence of a single character.
- Agreeing on the charset between writer and reader is necessary to interpret bytes accurately. A charset cannot be reliably inferred merely by inspecting an arbitrary byte array.

## 2. Creating Coders from Charset

```java
Charset charset = StandardCharsets.UTF_8;
CharsetEncoder encoder = charset.newEncoder();
CharsetDecoder decoder = charset.newDecoder();
```

This is a code snippet; `java.nio.charset.*` must be imported. Each call to `newEncoder()`/`newDecoder()` creates an encoding/decoding object with its own **state**. For UTF-8, the encoder reads UTF-16 units, checks surrogate pairs, and produces valid bytes. The decoder reads UTF-8 bytes, validates byte sequences, and produces corresponding `char`s.

There are two ways to use a coder:

1. **One-shot, entire content**: `encoder.encode(CharBuffer)` and `decoder.decode(ByteBuffer)`. These two methods perform a complete conversion session, including internal reset and flush; well-suited when all data is already available.
2. **Incremental, multi-chunk data**: `encoder.encode(CharBuffer, ByteBuffer, boolean endOfInput)` and `decoder.decode(ByteBuffer, CharBuffer, boolean endOfInput)`, followed by `flush(output)`. Suitable when data arrives in chunks, the output buffer has finite capacity, or conversion progress must be controlled.

Do not mix both styles within **the same active coder session**: the one-shot convenience method resets and finishes the conversion session, so calling it mid-way during incremental processing can trigger `IllegalStateException` or corrupt logic.

## 3. How Does Malformed Input Differ from Unmappable Character?

Both are conversion errors, yet their causes differ.

### 3.1. Malformed input: input violates the encoding rules

- **When decoding UTF-8**: byte `C3` requires a following continuation byte, so `C3 28` is invalid (byte `28` is an opening parenthesis, not a continuation byte). This is a **malformed** error.
- **When encoding from Java characters**: a high surrogate `char` (`\uD800`–`\uDBFF`) not followed by a valid low surrogate produces an invalid UTF-16 sequence; the encoder can report **malformed**.
- Truncated UTF-8 at the end of data is also a malformed error **once it is confirmed that no more bytes will arrive**. If more data might arrive on the next read, the coder can retain the incomplete portion and return `UNDERFLOW`.

### 3.2. Unmappable character: input is valid yet the target charset cannot represent it

- The Java string `"café"` is valid Unicode, yet **US-ASCII** has no byte code for `é`; when encoding as US-ASCII, this is an **unmappable** error.
- When decoding, some charsets can contain structurally valid byte sequences with no equivalent Unicode character; the decoder can likewise detect **unmappable**. Do not infer that every non-ASCII byte is classified identically by a US-ASCII decoder; exact classification belongs to the codec.

The two branches are configured separately: `onMalformedInput(action)` and `onUnmappableCharacter(action)`. Calling one **does not automatically** change the other.

### 3.3. Corresponding exceptions

Both `MalformedInputException` and `UnmappableCharacterException` extend `CharacterCodingException`; `CharacterCodingException` extends `IOException`. With one-shot `encode(CharBuffer)` / `decode(ByteBuffer)` and policy `REPORT`, errors usually surface as these exceptions. With incremental calls, errors are reported in **`CoderResult`**, unless the caller calls `throwException()` to turn them into an exception.

## 4. CodingErrorAction: REPORT, REPLACE, and IGNORE

```java
encoder.onMalformedInput(CodingErrorAction.REPORT);
encoder.onUnmappableCharacter(CodingErrorAction.REPORT);

decoder.onMalformedInput(CodingErrorAction.REPLACE);
decoder.onUnmappableCharacter(CodingErrorAction.REPLACE);
```

The lines above are a snippet where `encoder`/`decoder` have already been created via `Charset.newEncoder()` / `newDecoder()`.

| Action | What happens on invalid input | Benefit | Risk |
| --- | --- | --- | --- |
| `REPORT` | Returns an error `CoderResult` or throws `CharacterCodingException`, depending on API | Detects errors, avoids silent data loss | Requires error-flow handling |
| `REPLACE` | Drops the erroneous segment and writes a replacement string/bytes | Allows displaying remaining corrupted data | Original information is no longer intact |
| `IGNORE` | Discards the erroneous segment completely and processes what follows | Suitable only when dropping data is allowed | Loses characters, can distort content meaning |

**Replacement values differ in the two directions**:

- An encoder replaces erroneous characters with **`byte[]`**; US-ASCII normally uses byte `3F` (character `?`), though the actual value depends on the charset/encoder. You can call `encoder.replaceWith(byte[])` with a valid byte sequence accepted by the codec.
- A decoder replaces erroneous bytes with **`String`**; the default value is normally the Unicode Replacement Character `U+FFFD` (symbol `�`). You can call `decoder.replaceWith(String)` with a valid replacement string.

Do not infer that an encoder can set `U+FFFD` as its replacement bytes; an encoder's replacement consists of **encoded bytes**, whereas a decoder's replacement consists of **Unicode characters**. The replacement policy and the replacement value are two separate settings.

**The default for a new coder object** (`newEncoder()` / `newDecoder()`) is **`REPORT` for both malformed and unmappable**. However, many high-level convenience APIs default to **replacement**. Do not infer from `new String(bytes, UTF_8)` or `String.getBytes(UTF_8)` that a new coder also defaults to `REPLACE`.

## 5. Runnable Example: Comparing the Three Error Policies

Save as `CodingErrorPolicies.java`, using JDK 17+:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class CodingErrorPolicies {
    public static void main(String[] args) {
        CodingErrorAction[] actions = {
                CodingErrorAction.REPORT,
                CodingErrorAction.REPLACE,
                CodingErrorAction.IGNORE
        };

        // "AéB" is valid Unicode, yet US-ASCII cannot encode 'é'.
        for (CodingErrorAction action : actions) {
            CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
                    .onMalformedInput(action)
                    .onUnmappableCharacter(action);
            try {
                ByteBuffer encoded = encoder.encode(
                        CharBuffer.wrap("A\u00E9B"));
                byte[] bytes = new byte[encoded.remaining()];
                encoded.get(bytes);
                System.out.println("encode " + action + ": "
                        + new String(bytes, StandardCharsets.US_ASCII));
            } catch (CharacterCodingException e) {
                System.out.println("encode " + action + ": "
                        + e.getClass().getSimpleName());
            }
        }

        // Malformed UTF-8: C3 requires a continuation byte, yet 28 is invalid.
        byte[] invalidUtf8 = {
                0x41, (byte) 0xC3, 0x28, 0x42
        };
        for (CodingErrorAction action : actions) {
            CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(action)
                    .onUnmappableCharacter(action);
            try {
                String decoded = decoder.decode(
                        ByteBuffer.wrap(invalidUtf8)).toString();
                // Print replacement character explicitly instead of relying on console fonts.
                System.out.println("decode " + action + ": "
                        + decoded.replace("\uFFFD", "<U+FFFD>"));
            } catch (CharacterCodingException e) {
                System.out.println("decode " + action + ": "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Compile/run:

```bash
javac CodingErrorPolicies.java
java CodingErrorPolicies
```

Stdout verified with JDK:

```text
encode REPORT: UnmappableCharacterException
encode REPLACE: A?B
encode IGNORE: AB
decode REPORT: MalformedInputException
decode REPLACE: A<U+FFFD>(B
decode IGNORE: A(B
```

Explanation of each case:

- `"AéB"` contains three visible characters; `é` is not in US-ASCII. With `REPORT` we get `UnmappableCharacterException`; `REPLACE` turns it into `?`; `IGNORE` drops `é` completely.
- Input bytes for the decoder are `41 C3 28 42`. `41`/`42` are `A`/`B` respectively and `28` is `(`. Byte `C3` cannot form a valid UTF-8 sequence with the following byte, so `REPORT` throws `MalformedInputException`; `REPLACE` substitutes only the erroneous segment while still reading `(B`, and `IGNORE` removes the erroneous segment.
- The demo creates **a new coder for each conversion**. This is the safe pattern when changing policies across independent inputs; never reuse a coder carrying leftover partial state.

## 6. Differences Between Direct Coders and Convenience APIs

APIs that look similar have **different error policies**:

| API | Purpose | Typical Error Policy Applied |
| --- | --- | --- |
| `charset.newEncoder().encode(CharBuffer)` | One-shot encoding with a new coder | Defaults to `REPORT`, may throw `CharacterCodingException` |
| `charset.newDecoder().decode(ByteBuffer)` | One-shot decoding with a new coder | Defaults to `REPORT`, may throw `CharacterCodingException` |
| `charset.encode(CharBuffer)` / `charset.decode(ByteBuffer)` | Convenience methods on `Charset` | Uses `REPLACE` policy |
| `String.getBytes(charset)` | Encodes entire `String` to bytes | May replace broken UTF-16; unsuitable if bad data must be rejected |
| `new String(byte[], charset)` | Decodes entire bytes to `String` | Replaces invalid byte sequences; not a UTF-8 validity checker |
| `new OutputStreamWriter(stream, charset)` | Writes characters to byte stream | Replaces invalid data by default during writing |
| `new InputStreamReader(stream, charset)` | Reads bytes into characters | Replaces invalid data by default during reading |

For instance, this line **is not strict UTF-8 validation**:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
```

`bytes` is an existing `byte[]`; if UTF-8 bytes are invalid, Java may substitute `U+FFFD` and return a `String`. When malformed data must be rejected, use:

```java
CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
String text = strict.decode(ByteBuffer.wrap(bytes)).toString();
```

This is a snippet; import `java.nio.*`, `java.nio.charset.*`, and handle `CharacterCodingException`. It reports errors instead of erasing traces of bad input. This is especially useful for upload validation, config formats requiring valid UTF-8, or protocols forbidding silent character alteration.

## 7. Buffers and CoderResult in Incremental Conversion

When reading from a network/file in chunks, you cannot assume a single `read` ends cleanly on a character boundary. Incremental API:

```java
CoderResult result = decoder.decode(
        inputBytes, outputChars, endOfInput);
```

Here `inputBytes` is a `ByteBuffer`, `outputChars` is a `CharBuffer`, and `endOfInput` is a `boolean`. For an encoder, the buffer directions reverse:

```java
CoderResult result = encoder.encode(
        inputChars, outputBytes, endOfInput);
```

`CoderResult` has four status categories:

- **`UNDERFLOW`**: all available input was processed **or** remaining input is insufficient to form the next character/byte. When the source is not exhausted, read more data; do not automatically equate `UNDERFLOW` with EOF.
- **`OVERFLOW`**: the output buffer lacks enough space. Drain the output buffer's contents to free space and call the coder again; do **not** treat this as a codec error.
- **`isMalformed()`**: the input sequence violates the charset structure. Returned only when the corresponding policy is `REPORT`.
- **`isUnmappable()`**: input is valid yet unrepresentable. Returned only when the corresponding policy is `REPORT`.

`result.length()` on an error `CoderResult` reports **the number of offending input units** (bytes for a decoder, `char`s for an encoder), not total bytes read since the start of the stream. `result.throwException()` turns the corresponding error status into `MalformedInputException`/`UnmappableCharacterException`. Never call `throwException()` blindly on `UNDERFLOW` or `OVERFLOW`.

### Single-session coder workflow

```text
reset() if reusing a coder that finished a previous session
   |
   v
encode/decode(input, output, false)
   |                 |
   | UNDERFLOW       | OVERFLOW
   v                 v
add input          drain output, continue
   |
   | until certain no more input remains
   v
encode/decode(remaining input, output, true)
   |
   | handle OVERFLOW if any, until UNDERFLOW
   v
flush(output)
   |
   | if OVERFLOW: drain output and call flush again
   v
session ends; reset before a new session
```

`endOfInput == true` means **these are the final bytes/chars in the entire conversion session**, not “the end of the current buffer.” Setting this flag too early can turn a character waiting for its remaining bytes into malformed input or violate coder state. If trailing data is genuinely incomplete when `endOfInput == true`, the codec must apply its configured error policy.

### Buffers: flip, compact, and clear

- `input.flip()` switches `input` from **writing new data into the buffer** to **reading by the coder**.
- After the coder returns `UNDERFLOW` while `input` still holds bytes/chars of an incomplete sequence, call `input.compact()` to preserve unconsumed units at the start of the buffer and then **append new data** after them. Calling `input.clear()` at this point would **lose** the remaining units.
- For `output`, when data is ready to be read/written downstream, call `output.flip()`, consume all of `output.remaining()`, and then call `output.clear()` to receive more results. If consuming only part of the output, use `compact()` or preserve the remainder.
- `position`/`limit` are advanced by the coder according to units read/written; do not use `array().length` instead of `remaining()` to determine valid content.
- If a single encoded unit or codec state requires more room than the current buffer, use a larger buffer or an appropriate fill/drain strategy. Do not spin on `OVERFLOW` with a full output buffer without freeing space.

## 8. Runnable Java 17+ Example: UTF-8 Split Across Two Chunks

The euro sign `€` (code point `U+20AC`) has UTF-8 bytes `E2 82 AC`. Suppose the network delivers only the first byte `E2` in the first read, and `82 AC` arrives in the second read. The decoder must **retain the incomplete byte** between reads and finish only once all data is known.

Save as `IncrementalUtf8Decoder.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class IncrementalUtf8Decoder {
    public static void main(String[] args) throws Exception {
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        ByteBuffer input = ByteBuffer.allocate(8);
        CharBuffer output = CharBuffer.allocate(8);

        // Chunk 1: first byte of the € character, not yet enough to decode.
        input.put((byte) 0xE2);
        input.flip();
        CoderResult first = decoder.decode(input, output, false);
        System.out.println("first: " + first
                + ", remaining=" + input.remaining()
                + ", chars=" + output.position());

        // compact() keeps E2; append 82 AC to form the complete E2 82 AC.
        input.compact();
        input.put((byte) 0x82).put((byte) 0xAC);
        input.flip();

        // Now the final bytes have been received.
        CoderResult last = decoder.decode(input, output, true);
        CoderResult flushed = decoder.flush(output);
        output.flip();

        int codePoint = Character.codePointAt(output, 0);
        System.out.println("finish: " + last
                + ", flush=" + flushed
                + ", codepoint=U+"
                + Integer.toHexString(codePoint).toUpperCase(Locale.ROOT));
    }
}
```

Run:

```bash
javac IncrementalUtf8Decoder.java
java IncrementalUtf8Decoder
```

Stdout verified with JDK:

```text
first: UNDERFLOW, remaining=1, chars=0
finish: UNDERFLOW, flush=UNDERFLOW, codepoint=U+20AC
```

In the first `decode(..., false)` call, `UNDERFLOW` and `remaining=1` mean the byte `E2` **has not been consumed**; the decoder needs more bytes to determine the character. `compact()` retains this byte, after which the program appends `82 AC`. The second `decode(..., true)` call completes `U+20AC`, and `flush` ends the session. The demo targets two specific chunks with ample buffer capacity; when processing long streams, you need a loop handling `OVERFLOW`, empty reads, EOF, and I/O errors per the real data source.

## 9. Error Policies in Incremental Conversion

Suppose `REPORT` is selected:

```java
CoderResult result = decoder.decode(input, output, false);

if (result.isMalformed() || result.isUnmappable()) {
    int invalidUnitCount = result.length();
    // Record error offset and length if needed by the application.
    // Do not advance position manually without knowing how to handle the data.
    result.throwException();
}
```

This is a snippet; `input`/`output`/`decoder` must be initialized properly and the calling method must handle `CharacterCodingException`. When a coder detects an error, `input.position()` points to the start of the erroneous sequence per the normal API contract; `result.length()` helps identify the offending span to report, yet **do not automatically skip** those bytes if the data policy requires rejecting the entire record.

If the application genuinely needs to skip errors and continue, it is better to explicitly select `IGNORE` or `REPLACE` and verify whether that policy fits business requirements. Trying to shift `ByteBuffer.position` manually to “recover” can drop bytes, trigger infinite loops, or turn malicious input into unintended text.

**Atomicity note:** When `REPORT` occurs after some valid data, `output` may already contain characters/bytes produced before the error. Do not treat incremental conversion as a self-rolling-back transaction. If the system accepts only completely valid data, validate first before committing output or keep output in a staging area.

## 10. Customizing Replacement Values

Example controlling a US-ASCII encoder:

```java
CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
        .onUnmappableCharacter(CodingErrorAction.REPLACE)
        .replaceWith(new byte[] { (byte) '!' });
ByteBuffer bytes = encoder.encode(CharBuffer.wrap("A\u00E9B"));
// ASCII result is "A!B".
```

Example controlling a UTF-8 decoder:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .replaceWith("[?]");
CharBuffer chars = decoder.decode(ByteBuffer.wrap(
        new byte[] { 0x41, (byte) 0xC3, 0x28, 0x42 }));
// With a charset/replacement limit allowing it, the result would be "A[?](B".
```

**The two examples above are illustrative snippets; do not copy the second decoder example verbatim while ignoring replacement-length constraints:** `CharsetDecoder.replaceWith(String)` only accepts a non-empty replacement string whose length does not exceed `maxCharsPerByte()`; for a typical JDK UTF-8 decoder, the 3-character string `"[?]"` **exceeds the limit** and throws `IllegalArgumentException`. A **valid, runnable** configuration is `decoder.replaceWith("?")`, which yields `"A?(B"`.

Therefore, for real decoder replacement, write:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .replaceWith("?");
```

This snippet configures replacing malformed UTF-8 bytes with the `?` character. Similarly, `CharsetEncoder.replaceWith(byte[])` validates that the byte array is non-empty and its length/values are legal for the charset; you cannot pass an arbitrary byte sequence from another encoding.

## 11. Using with Reader and Writer at I/O Boundaries

Configured coders can be attached to Java streams:

```java
CharsetDecoder strictDecoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(inputStream, strictDecoder)) {
    // Read characters; receiving invalid UTF-8 bytes may throw IOException.
}

CharsetEncoder strictEncoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Writer writer = new OutputStreamWriter(outputStream, strictEncoder)) {
    // Write characters; broken UTF-16 may cause IOException.
}
```

These are two **separate snippets**: import `java.io.*`, `java.nio.charset.*`; `inputStream` and `outputStream` are already-opened streams owned by the current code. `InputStreamReader`/`OutputStreamWriter` manage buffering and use the configured coder. Closing the wrapper also closes the underlying stream; if the stream is owned elsewhere (such as `System.out` or a shared socket), coordinate lifecycle ownership.

Do not share **the same instance** of `CharsetEncoder` or `CharsetDecoder` concurrently across multiple threads: coders are stateful and the API **is not thread-safe**. Use a dedicated coder per process/conversion, or synchronize strictly if reuse is unavoidable. `reset()` initializes a fresh session after the previous session has ended/aborted cleanly; it does not replace locking.

## 12. Choosing a Policy Based on Business Requirements

| Scenario | Recommendation | Why |
| --- | --- | --- |
| Reading protocol data requiring valid UTF-8 | `CharsetDecoder` + `REPORT` | Avoids silently turning bad data into different data |
| Processing an import file requiring logging damaged lines | `REPORT`, track offset and report error | Preserves error evidence for user correction |
| Previewing corrupted text in a UI | May use `REPLACE`, with notice that data was substituted | Still displays remaining readable content |
| Exporting Vietnamese text to an ASCII-only codec | Prefer UTF-8; if ASCII is mandatory, use `REPORT` or an explicit lossy policy | Prevents silently losing accents/names |
| Sanitizing data per a rule allowing dropping bad characters | `IGNORE` only when explicitly permitted by spec | Dropping data is a business decision, not lossless recovery |
| Reading chunks from network, NIO channels | Incremental coder, retain partial buffer, handle `UNDERFLOW`/`OVERFLOW` | Chunks are not guaranteed to align with character boundaries |

Do not use `IGNORE` as a “safe fix” for untrusted input. For example, identifier strings, digital signatures, path checks, access permissions, or protocol syntax can change meaning when bytes/chars are deleted. For critical data, prefer **rejecting invalid input** and reporting the offset/error clearly; if using `REPLACE`, disclose that the data is no longer verbatim.

## 13. Limits to Distinguish

### Charsets do not automatically fix previously mis-encoded data

If a file was previously written with the wrong charset, `CharsetDecoder` cannot deduce what it “should have been.” For instance, decoding UTF-8 bytes with another charset can produce characters that are **technically valid yet semantically wrong** (*mojibake*), which `REPORT` may **not** detect. Proper decoding relies on metadata/protocol contracts, not merely byte-syntax validation.

### Charsets are not synonymous with Unicode normalization

`"é"` can be represented as one code point `U+00E9` or two code points `U+0065 U+0301`. Both encode to valid UTF-8, yet produce different bytes. `CharsetEncoder` does not automatically normalize NFC/NFD; if business logic requires canonical comparison, use `java.text.Normalizer` with clear rules before/after conversion. Do not normalize sensitive identifiers arbitrarily.

### Byte Order Mark (BOM) and charset detection

Some formats use a BOM to signal byte order or encoding. `CharsetDecoder` is not an encoding-detection library for arbitrary content; whether a BOM is handled depends on the charset and how you pick the decoder. For UTF-8, do not assume every file has a BOM or strips it identically. Define an explicit BOM policy when reading/writing protocols.

### Size estimation and finishing streams

`encoder.averageBytesPerChar()`, `maxBytesPerChar()`, `decoder.averageCharsPerByte()`, and `maxCharsPerByte()` provide helpful estimates/bounds for buffer allocation; they **do not replace** actual conversion results when exact sizes are required. With codec state and `OVERFLOW`, proper buffer handling is still mandatory.

`flush()` on a coder **is not** `OutputStream.flush()`: `coder.flush` writes any remaining state from the encoding into **the output buffer you supply**, normally called **after the final encode/decode call with `endOfInput=true`**. Afterward, the application must still drain data from `ByteBuffer`/`CharBuffer` to the destination. When using `Reader`/`Writer`, the wrapper layer manages much of this workflow.

### Do not treat a coder as a complete security validator

`REPORT` validates compliance **only against a specific charset**. It does not check JSON schema validity, URL safety, Unicode confusables, forbidden control characters, HTML escaping, or checksums. After encoding/decoding, syntax and security validation of the data are still required.

## 14. Common Mistakes and Fixes

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Using `new String(bytes, UTF_8)` to validate UTF-8 | Bad bytes may be replaced without warning | `UTF_8.newDecoder()` + `REPORT` |
| Assuming `newDecoder()` defaults to `REPLACE` | Unexpected exceptions | Remember new coders default to `REPORT` |
| Configuring only `onMalformedInput` and forgetting `onUnmappableCharacter` | Both error groups handled inconsistently | Set both policies explicitly |
| Treating malformed and unmappable as the same error | Misleading root-cause reporting | Distinguish structurally invalid input from unrepresentable characters |
| Calling `input.clear()` when decoder returns `UNDERFLOW` with leftover bytes | Loses half a UTF-8 character | Call `compact()` before loading new bytes |
| Passing `endOfInput=true` on every network chunk | Treats incomplete bytes as truncated input | Set `true` only when EOF is confirmed |
| Looping on `OVERFLOW` without draining output | Fails to make progress | `flip`, drain, `clear/compact`, then continue |
| Forgetting coder `flush(output)` at end of session | Stateful charsets may miss trailing output | Finish the final encode/decode pass then flush the coder |
| Using one coder instance concurrently across threads | Corrupted state/races | One coder per session/thread, or synchronize |
| Choosing `IGNORE` to “fix” critical data | Character loss, altered meaning | `REPORT` and handle errors per specification |
| Confusing `replaceWith(byte[])` and `replaceWith(String)` | Wrong conversion direction or exception | Encoder replaces bytes; decoder replaces `String`, obeying limits |
| Assuming a decoder guarantees semantically valid content | Mojibake can still be valid in the wrong charset | Agree on charset via protocol and validate decoded data |

## 15. Self-Check Questions

1. **Difference in data direction?** `CharsetEncoder` takes `char` to produce bytes; `CharsetDecoder` takes bytes to produce `char`.
2. **Why does encoding `"AéB"` as US-ASCII with `REPORT` fail?** `é` is valid Unicode yet unrepresentable in US-ASCII: `UnmappableCharacterException`.
3. **Why can't bytes `C3 28` be decoded as standard UTF-8?** `C3` starts a two-byte sequence yet `28` is not a continuation byte: malformed.
4. **How does `REPORT` differ from `REPLACE` and `IGNORE`?** It reports an error rather than substituting or deleting the offending segment.
5. **What policy does `newDecoder()` default to?** `REPORT`; do not confuse it with `Charset.decode(...)` or `new String(bytes, charset)`, which typically replace errors.
6. **Does `UNDERFLOW` always mean EOF?** No; it may simply mean bytes/chars for the next character are still missing.
7. **Why call `compact()` on input with leftover bytes?** To keep unconsumed bytes and join them with bytes from the next chunk.
8. **When is `endOfInput=true` set?** When no more input remains in the entire conversion **session**, not at the end of a temporary chunk.
9. **What does `flush(output)` belong to?** `CharsetEncoder`/`CharsetDecoder`; it flushes codec state into the output buffer after the final input pass.
10. **What is needed to prevent silent data loss when reading UTF-8?** Create `UTF_8.newDecoder()`, configure both error groups to `REPORT`, handle `CharacterCodingException`, and avoid committing content on failure.

## Java SE 17 API References

- [`CharsetEncoder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html).
- [`CharsetDecoder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [`CodingErrorAction` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html).
- [`CoderResult` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CoderResult.html).
- [`Charset` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html).
- [`InputStreamReader` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html).
- [`OutputStreamWriter` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html).

**Remember:** Coders perform conversion per a charset; `CodingErrorAction` determines whether invalid data is reported, replaced, or ignored; `CoderResult` guides how each incremental pass is handled. To process text correctly, agree on the charset, choose an appropriate error policy, and respect coder state and buffers.