# `CharsetEncoder`, `CharsetDecoder`, and the `REPORT` Policy in Java

When exchanging data with files, networks, or other systems, an application must convert between Unicode character strings and byte sequences. `CharsetEncoder` and `CharsetDecoder` allow you to perform this conversion in a controlled way; `CodingErrorAction.REPORT` requires **detecting and reporting unconvertible data**, instead of silently replacing or dropping characters. This is the right choice whenever data integrity matters.

## 1. Foundations: Characters, Bytes, and Charsets

- `String` stores Unicode text as Java UTF-16 code units. A character outside the BMP can occupy two `char`s (a surrogate pair), so one `char` does not always correspond to one complete Unicode character.
- `Charset` defines the mapping rules between characters and bytes, such as `StandardCharsets.UTF_8` or `StandardCharsets.US_ASCII`.
- **Encoding** (text encoding): `CharBuffer` → `CharsetEncoder` → `ByteBuffer`.
- **Decoding** (byte decoding): `ByteBuffer` → `CharsetDecoder` → `CharBuffer`.
- `ByteBuffer` and `CharBuffer` have `position`, `limit`, and `capacity`. The encoder/decoder reads from the input's current `position` and writes at the output's current `position`. After writing manually, call `flip()` before reading; before writing more into a partially read buffer, call `compact()` if you need to keep unprocessed data.

The same byte sequence can carry different meanings under different charsets. Therefore, you must know the charset from the protocol or data contract; you cannot infer the right charset using `REPORT` alone.

## 2. Roles of the APIs

| API | Role |
| --- | --- |
| `Charset.newEncoder()` | Creates a character-to-byte encoder for the chosen charset. |
| `Charset.newDecoder()` | Creates a byte-to-character decoder for the chosen charset. |
| `CodingErrorAction.REPORT` | Stops and reports an error upon encountering malformed or unmappable data. |
| `CodingErrorAction.REPLACE` | Uses a replacement string/byte on error and continues processing. |
| `CodingErrorAction.IGNORE` | Skips the offending data and continues processing. |
| `CharacterCodingException` | Common checked exception superclass for conversion errors from convenience methods. |
| `MalformedInputException` | Input is invalid according to the encoding's structural rules. |
| `UnmappableCharacterException` | Input is structurally valid, but has no mapping in the target encoding. |
| `CoderResult` | Result of each conversion step: `UNDERFLOW`, `OVERFLOW`, malformed, or unmappable. |

### How Do Malformed and Unmappable Differ?

| Direction | Malformed | Unmappable |
| --- | --- | --- |
| Decode (byte → char) | Bytes violate the charset's structure; e.g., `C3 28` is not a valid UTF-8 sequence. | Byte sequence is structurally valid for the charset, yet cannot be mapped to a Unicode character; whether this occurs depends on the charset. |
| Encode (char → byte) | Structurally invalid UTF-16 character input, such as an unpaired high surrogate (`U+D800`). | Valid Unicode character that the target charset cannot represent; e.g., `€` with US-ASCII. |

Error classification is determined by the active charset. Not every charset produces both error types in practice.

## 3. Configuring `REPORT` Properly

Create the encoder and decoder from an explicit charset; configure both **malformed input** and **unmappable character**:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
    .onMalformedInput(CodingErrorAction.REPORT)
    .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
    .onMalformedInput(CodingErrorAction.REPORT)
    .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

The snippet above shows configuration inside a method or program that already imports `java.nio.charset.*`; see the complete program in the next section.

A fresh encoder/decoder in Java already defaults to `REPORT`; it is still good practice to declare it explicitly to document the data contract and avoid omissions when reusing an object whose configuration was changed. Both policies should be set because there are two independent error causes.

**Crucial difference between the two API styles:**

- With `encoder.encode(CharBuffer)` and `decoder.decode(ByteBuffer)` (one-shot convenience methods), a `REPORT` error is thrown as `CharacterCodingException`, typically one of the two subclasses in the table above.
- With `encoder.encode(in, out, endOfInput)` and `decoder.decode(in, out, endOfInput)` (step-by-step streaming API), a `REPORT` error **returns an error `CoderResult`**. The caller must check `result.isError()`, then call `result.throwException()` or handle it explicitly. Simply configuring `REPORT` while ignoring `CoderResult` can still leave the application failing to handle errors properly.
- `REPLACE` and `IGNORE` alter the data. Use them when the business logic intentionally accepts data loss; do not use them to validate intact input.

## 4. Java 17+ Program: Reporting Errors Explicitly

Save the following as **StrictCharsetDemo.java** (UTF-8). The example creates a dedicated encoder and decoder for each case, intentionally constructing three kinds of input to observe the exceptions.

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.*;

public class StrictCharsetDemo {
    static CharsetDecoder strictDecoder(Charset charset) {
        return charset.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);
    }

    static CharsetEncoder strictEncoder(Charset charset) {
        return charset.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);
    }

    public static void main(String[] args) throws CharacterCodingException {
        ByteBuffer bytes = strictEncoder(StandardCharsets.UTF_8)
            .encode(CharBuffer.wrap("Cà phê"));
        String text = strictDecoder(StandardCharsets.UTF_8)
            .decode(bytes).toString();
        System.out.println("Round-trip UTF-8: " + text);

        try {
            strictDecoder(StandardCharsets.UTF_8)
                .decode(ByteBuffer.wrap(
                    new byte[] {(byte) 0xC3, (byte) 0x28}));
        } catch (MalformedInputException ex) {
            System.out.println(
                "Malformed UTF-8: " + ex.getClass().getSimpleName());
        }

        try {
            strictEncoder(StandardCharsets.US_ASCII)
                .encode(CharBuffer.wrap("A€B"));
        } catch (UnmappableCharacterException ex) {
            System.out.println(
                "Unmappable ASCII: " + ex.getClass().getSimpleName());
        }

        try {
            strictEncoder(StandardCharsets.UTF_8)
                .encode(CharBuffer.wrap(new char[] {'\uD800'}));
        } catch (MalformedInputException ex) {
            System.out.println(
                "Malformed surrogate: " + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 StrictCharsetDemo.java
java StrictCharsetDemo
~~~

Expected output:

~~~text
Round-trip UTF-8: Cà phê
Malformed UTF-8: MalformedInputException
Unmappable ASCII: UnmappableCharacterException
Malformed surrogate: MalformedInputException
~~~

**Explanation:** The text "Cà phê" is fully representable in UTF-8, so it round-trips cleanly. Byte `C3` starts a two-byte sequence in UTF-8, yet `28` is not a continuation byte, so the decoder reports malformed input. The character `€` is valid, but US-ASCII cannot encode it, so the encoder reports an unmappable character. A lone high surrogate does not form valid UTF-16, so the UTF-8 encoder reports malformed input. Exceptions are caught separately to pinpoint the failure type; in real applications, log context such as the data source and processing offset while avoiding writing sensitive data to logs.

## 5. Streaming Decode: Distinguishing Temporary Missing Bytes from Corrupted Data

A UTF-8 character can be split across two byte reads. If the first chunk contains `E2 82` (the first two bytes of `€`), the decoder cannot yet declare corruption while **more data is still expected**. Call `decode(..., false)` to get `UNDERFLOW`, keep the two unused bytes, feed `AC`, then call `decode(..., true)` once the end of input is reached. Finally, call `flush(...)`.

The standalone program **IncrementalDecodeDemo.java** illustrates this flow using buffers large enough not to trigger `OVERFLOW`:

~~~java
import java.nio.*;
import java.nio.charset.*;

public class IncrementalDecodeDemo {
    public static void main(String[] args)
            throws CharacterCodingException {
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);
        ByteBuffer input = ByteBuffer.allocate(8);
        CharBuffer output = CharBuffer.allocate(8);

        input.put(new byte[] {(byte) 0xE2, (byte) 0x82});
        input.flip();
        CoderResult first = decoder.decode(input, output, false);
        if (first.isError()) first.throwException();
        System.out.println(
            "Pass 1: " + first
            + ", remaining bytes: " + input.remaining());

        input.compact(); // Keep the two undecoded bytes.
        input.put((byte) 0xAC);
        input.flip();
        CoderResult last = decoder.decode(input, output, true);
        if (last.isError()) last.throwException();
        if (!last.isUnderflow()) {
            throw new IllegalStateException("Output buffer too small");
        }

        CoderResult flushed = decoder.flush(output);
        if (flushed.isError()) flushed.throwException();
        if (!flushed.isUnderflow()) {
            throw new IllegalStateException("Output buffer too small");
        }

        output.flip();
        System.out.println("Result: " + output);
    }
}
~~~

~~~bash
javac -encoding UTF-8 IncrementalDecodeDemo.java
java IncrementalDecodeDemo
~~~

~~~text
Pass 1: UNDERFLOW, remaining bytes: 2
Result: €
~~~

On the first pass, the decoder does not consume the two incomplete bytes; `compact()` moves them to the beginning of the buffer, leaving room for new bytes. After receiving `AC` and signaling end of input, the decoder completes the `€` character. If `endOfInput=true` had been passed on the first chunk, the two incomplete bytes would be treated as malformed input at end-of-stream and `REPORT` would report an error.

### Loop for Finite-Sized Buffers

The example above has only one character and buffers large enough to hold it. For longer data or small buffers, loop over `CoderResult`:

1. Fill bytes, `flip()` the input, then call `decode(input, output, endOfInput)`.
2. If `isError()`, call `throwException()` or handle it explicitly per the error policy; do not ignore it.
3. If `isOverflow()`, drain the characters currently in `output` (typically `flip()`, read, then `clear()` or `compact()`) and continue decoding with the remaining input.
4. If `isUnderflow()` and the stream has not ended, preserve undecoded bytes with `input.compact()` and read more; do not discard trailing bytes of a chunk. If the stream has ended, proceed to `flush(output)` and also handle `OVERFLOW` until flush returns `UNDERFLOW`.
5. When reusing the same decoder for **a new conversion session**, call `reset()` before starting. Never share a stateful encoder/decoder across threads.

Step-by-step encoding follows a similar structure with `encode(CharBuffer, ByteBuffer, endOfInput)`, followed by `flush(ByteBuffer)`. Do not confuse `UNDERFLOW` with "entire conversion succeeded": when `endOfInput=false`, it can also mean trailing bytes in the chunk are not yet enough to form a character.

## 6. `REPORT` vs. Common Convenience Conversions

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
byte[] raw = text.getBytes(StandardCharsets.UTF_8);
~~~

These two convenience calls are handy for trusted text, but malformed/unmappable cases can be silently **replaced** per their API contracts. They do not offer a `CodingErrorAction.REPORT` option. For data requiring strict verification, use `newDecoder()` / `newEncoder()` and configure both error policies.

When reading from an `InputStream`, you can pass a configured decoder to `InputStreamReader(InputStream, CharsetDecoder)`. Likewise, `OutputStreamWriter(OutputStream, CharsetEncoder)` accepts a configured encoder. This integrates strict policies into stream reading/writing; you still must handle `IOException` properly and close/flush streams cleanly.

## 7. Common Mistakes and How to Avoid Them

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Not passing an explicit charset | Behavior depends on environment config/contract and can diverge across systems. | Use the agreed charset, typically `StandardCharsets.UTF_8`. |
| Using `REPLACE` when bytes/characters must be preserved | Data is replaced without notifying business logic. | Choose `REPORT` and handle the exception or error result. |
| Only setting `onMalformedInput(REPORT)` | Unmappable errors may remain unhandled under a different policy. | Configure both `onMalformedInput` and `onUnmappableCharacter`. |
| Thinking `decode(in, out, ...)` always throws immediately | In the step-by-step API, `REPORT` returns an error `CoderResult`. | Check `isError()` and call `throwException()`. |
| Signaling end of stream too early | A multi-byte character split across chunks is flagged as malformed. | Use `endOfInput=false` for non-final chunks; preserve remaining bytes. |
| Ignoring `OVERFLOW` | Output buffer is full and remaining input is left unprocessed. | Drain the output buffer and continue calling. |
| Forgetting `flip()/compact()/flush()/reset()` | Wrong `position`/`limit`, lost bytes, dropped characters, or stale session state. | Follow the buffer and coder lifecycle strictly. |
| Treating `REPORT` as a way to auto-detect wrong charsets | Bytes can be valid in the wrong charset while the text is still nonsense. | Use charset metadata from the contract/protocol, BOM where defined, and domain-level content checks. |

## 8. Practical Application Tips and Self-Check

- **Strict CSV/JSON import:** Specify UTF-8, decode with a `REPORT` decoder, and reject files with malformed bytes before parsing content. Note that valid UTF-8 can still violate schema rules; validate schema separately.
- **Exporting to a system with a restricted charset:** Encode with `REPORT` to know immediately when text contains unexportable characters; request corrected input or negotiate another charset instead of losing characters.
- **Receiving data over a socket:** Preserve incomplete bytes between reads, and only pass `endOfInput=true` when the message or stream actually ends per the protocol.

Answer these three questions yourself: (1) Why does `C3 28` cause a UTF-8 decoder to report `MalformedInputException`? (2) Why does `€` cause `UnmappableCharacterException` with a US-ASCII encoder? (3) If you receive `E2 82` and then `AC` in two separate reads, why must you keep the leftover bytes and not pass `endOfInput=true` on the first read?

**Key point:** `REPORT` makes invalid data observable and actionable. With one-shot methods, handle `CharacterCodingException`; with the step-by-step API, handle `CoderResult`, buffer state, and the `decode/encode → flush → reset` lifecycle properly.
