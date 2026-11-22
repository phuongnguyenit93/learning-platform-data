# CharsetDecoder and CharsetEncoder for Incremental Data Conversion in Java NIO

**Topic:** Java Advance - networking  
**Group:** Buffers and Channels

In TCP networking, a single **SocketChannel.read(...)** or **InputStream.read(...)** call only receives **a portion of the available bytes**, with no guarantee of aligning to a complete character or a complete message. If the encoding is UTF-8, the **€** character takes 3 bytes; the **😄** emoji takes 4 bytes. A read call may stop right after the first byte of a character. Similarly, Java stores text in **UTF-16 code units**: an emoji typically consists of **two chars** (a surrogate pair), and the two halves may arrive in two different data-feeding turns to the encoder.

**java.nio.charset.CharsetDecoder** incrementally converts **byte → char**; **CharsetEncoder** incrementally converts **char → byte**. Unlike calling **new String(chunk, UTF_8)** or **text.getBytes(UTF_8)** on each independent chunk, these two converters maintain **the state of a conversion session**, report **UNDERFLOW / OVERFLOW / MALFORMED / UNMAPPABLE**, and allow precise control over when the stream ends.

This lesson focuses on **ByteBuffer**, **CharBuffer**, the **decode/encode** loop, handling split characters, **flush**, error behavior, and channel integration. **Do not confuse** charset conversion with message boundary framing, TCP framing, or confirming that the peer has processed the data.

## 1. The Problem: Byte Boundaries Are Not Character Boundaries

Example Java string:

~~~text
Text: A€😄Z
Code points: U+0041, U+20AC, U+1F604, U+005A
UTF-16 char units: [0041] [20AC] [D83D DE04] [005A] (5 char units)
UTF-8 bytes: 41 E2 82 AC F0 9F 98 84 5A (9 bytes)
~~~

With a TCP stream, reads can be split arbitrarily:

~~~text
Read #1: 41 E2
Read #2: 82
Read #3: AC F0 9F
Read #4: 98 84 5A
~~~

At the end of read #1, **E2** is not enough for the 3 bytes needed to form **€**. In read #3, **F0 9F** is not enough for the 4 bytes needed to form **😄**. If you construct **new String(byteChunk, UTF_8)** on each chunk, Java may replace incomplete or invalid byte sequences with **U+FFFD (�)**; concatenating the misdecoded strings will **not** reconstruct the original text.

In the encoding direction, a **CharBuffer** fragment may end at the **high surrogate U+D83D**; the **low surrogate U+DE04** arrives in the next fragment. You must not turn an isolated high surrogate into a **?** character, or treat it as a complete Unicode character on its own.

**Solution:** maintain a single **CharsetDecoder/CharsetEncoder** across all fragments of **the same encoding stream**, retain unconsumed input data, and only mark the end when you truly reach the end of the stream or a text unit defined as self-contained.

## 2. Four Core APIs and Relationships Between Buffers

~~~text
Receiving direction (decode):
socket/channel → [ByteBuffer, write mode]
                  flip()
              → CharsetDecoder.decode(inputBytes, outputChars, endOfInput)
              → [CharBuffer, write mode]
                  flip() → read decoded chars → clear()
                  compact() ByteBuffer to retain unconsumed bytes

Sending direction (encode):
string/char stream → [CharBuffer, write mode]
                     flip()
                 → CharsetEncoder.encode(inputChars, outputBytes, endOfInput)
                 → [ByteBuffer, write mode]
                     flip() → send/write all bytes → clear()/compact()
                     compact() CharBuffer to retain remaining chars

End of session: decode(..., true) or encode(..., true) → flush(output)
~~~

| Object/API | Input | Output | Role |
| --- | --- | --- | --- |
| **Charset** | Charset name / constant **StandardCharsets.UTF_8** | Decoder or encoder | Defines the byte ↔ character mapping |
| **CharsetDecoder** | **ByteBuffer** | **CharBuffer** | Incremental decoding, manages decoding state |
| **CharsetEncoder** | **CharBuffer** | **ByteBuffer** | Incremental encoding, manages encoding state |
| **CoderResult** | Result from decode/encode/flush | Status or error | Decides whether to read more, drain output, or report an error |
| **CodingErrorAction** | REPORT / REPLACE / IGNORE | Policy on invalid data | Handles malformed bytes / unmappable characters |

Creating the converters:

~~~java
import java.nio.charset.*;

CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

This is a configuration **snippet**; it does not perform I/O yet. Use a separate **newDecoder() / newEncoder()** for each independent session; encoder/decoder objects **are stateful and not safe for concurrent use by multiple threads**. **StandardCharsets.UTF_8** is a shareable Charset object; that does not apply to encoders/decoders.

## 3. Mastering position, limit, flip, compact, and clear

A **ByteBuffer/CharBuffer** has **capacity**, **position**, and **limit**. The converter reads from **input.position()** to **input.limit()** and writes into **output.position()** to **output.limit()**. After the call, the positions of both buffers may have changed; **do not assume all input was consumed**.

| Operation | Meaning |
| --- | --- |
| **flip()** | After writing data into a buffer, switch to reading: limit ← position, position ← 0 |
| **compact()** | Move **unread** data to the beginning, position after remaining data, limit ← capacity; prepare to write more |
| **clear()** | position ← 0, limit ← capacity; **does not erase physical contents**, only prepares for reuse and treats old contents as no longer needed |
| **hasRemaining()** | Whether elements remain between position and limit |
| **remaining()** | Number of remaining elements in the current region |
| **rewind()** | Resets position to 0 while keeping limit; usually **does not** replace compact when unconsumed input must be preserved |

The key loop on the decoder side:

~~~text
(1) ByteBuffer is in WRITE MODE, containing new bytes and leftover old bytes
(2) input.flip()                   → READ MODE
(3) decoder.decode(input, output, endOfInput)
(4) output.flip() → consume chars → output.clear()
(5) OVERFLOW: return to (3), after draining output
    UNDERFLOW: need more bytes or reached end of input
    ERROR: handle error according to policy
(6) input.compact()                → retain unconsumed bytes, switch to WRITE MODE
(7) receive more bytes and repeat
~~~

**Classic bug:** when **decode** returns **UNDERFLOW** because bytes at the end of the buffer do not yet form a complete character, calling **input.clear()** discards the exact bytes that must be kept. You must use **input.compact()**. On the other hand, once **output** has been completely read, it can be **clear()**ed to make room for new writes.

**Do not always call compact after encoding into a ByteBuffer if the channel has not written everything:** unsent output bytes must be preserved. When **channel.write(output)** returns **0** or writes only partially, the output buffer must remain in **read mode** to continue writing when the channel becomes ready, rather than discarding unsent data.

## 4. CoderResult: UNDERFLOW, OVERFLOW, Coding Errors

The call:

~~~java
CoderResult status = decoder.decode(inputBytes, outputChars, endOfInput);
~~~

can return:

| Result | Meaning | Proper handling |
| --- | --- | --- |
| **UNDERFLOW** | The converter cannot/has no more to process with the current input; a partial character with insufficient bytes/chars may remain | Preserve remaining input via **compact()**; read new input, or finalize if at end-of-input |
| **OVERFLOW** | Output buffer no longer has enough space to produce further results | **flip → consume/drain output → clear/compact → retry** with the remaining input |
| **MALFORMED** | Byte sequence / UTF-16 code units are **invalid** for the charset | REPORT error, or deliberately REPLACE/IGNORE |
| **UNMAPPABLE** | Valid character, but the target charset **cannot represent it** (typically US-ASCII encountering **€**) | REPORT or REPLACE/IGNORE per protocol |

In Java:

~~~java
if (status.isOverflow()) {
    // Drain output; then continue calling decode/encode.
} else if (status.isUnderflow()) {
    // Retain unconsumed input and wait for more, or proceed to finalization.
} else if (status.isError()) {
    status.throwException(); // CharacterCodingException subtype.
}
~~~

This is a **logic snippet**, not a standalone program. With **CodingErrorAction.REPORT**, errors such as **MALFORMED[1]** or **UNMAPPABLE[1]** are returned as a **CoderResult**; **throwException()** throws **MalformedInputException** or **UnmappableCharacterException** (subtypes of **CharacterCodingException**).

**UNDERFLOW does not necessarily mean input.position() == input.limit().** The decoder may stop at an incomplete byte sequence; if endOfInput=false, it cannot yet tell whether that is invalid data or a character that will be completed on the next turn. **OVERFLOW** is not a data error; it is a signal to drain the output.

**Preventing infinite loops:** if the output buffer is too small to hold **a minimum output unit** (for example, a CharBuffer with capacity=1 when the decoder needs to write **two UTF-16 chars** for a supplementary code point), you may keep receiving **OVERFLOW** even when the buffer is empty. Choose a sufficiently large output size, or expand the buffer when no progress is made. For the UTF-8 demo, **CharBuffer capacity 2** and **ByteBuffer output capacity 4** are enough for one code point of up to 4 UTF-8 bytes and two UTF-16 code units.

## 5. Fragmented decode(...): Preserving Incomplete Byte Sequences

**CharsetDecoder.decode(ByteBuffer in, CharBuffer out, boolean endOfInput)** converts the available input and may consume **fewer bytes than are currently present**.

Example when decoding **E2 82 AC** (the **€** character) byte by byte:

~~~text
decode([E2], endOfInput=false)          → UNDERFLOW; keep E2
decode([E2 82], endOfInput=false)       → UNDERFLOW; keep E2 82
decode([E2 82 AC], endOfInput=false)    → produces '€'; status is typically UNDERFLOW
~~~

One way to build the pipeline:

1. Use the input **ByteBuffer** in write mode; leftover data from the previous turn has already been compacted to the front.
2. Receive more bytes from **SocketChannel.read(buffer)** or a similar producer.
3. Call **flip()** to switch to read mode.
4. Call **decoder.decode(...)** in a loop; each time, **drain the CharBuffer** that the decoder has written into.
5. On **OVERFLOW**, drain output and immediately continue decoding; on **UNDERFLOW**, compact input to retain leftover bytes.
6. When **read() == -1**, set **endOfInput=true** on the final decode call, then call **flush(...)**.
7. If the protocol wraps a **self-contained text** inside a frame instead of ending at socket close, you may treat **end of frame** as end-of-input for that dedicated charset session, provided the protocol truly guarantees each frame contains an independently and completely encoded byte sequence.

### Nuances with Non-Blocking Channels

**read() == 0** means no bytes are available at that moment; it is **not** equivalent to EOF. Only **read() == -1** indicates end-of-stream for **SocketChannel**. Do not call **decode(..., true)** just because a read returned 0 or no more packets arrived temporarily. With non-blocking NIO, keep the input buffer + decoder in **per-connection** state and wait for **OP_READ** or the next event to supply more bytes.

After **UNDERFLOW**, you must check that the input buffer still has room to receive more data. If it is full and cannot consume data, use a larger buffer or report a resource limit error. You cannot decode indefinitely into a fixed buffer that is too small without a strategy to grow capacity or enforce protocol limits.

## 6. Fragmented encode(...): Watch Out for Surrogate Pairs and Partial Writes

**CharsetEncoder.encode(CharBuffer in, ByteBuffer out, boolean endOfInput)** encodes available chars into bytes. A Java **char** is a **UTF-16 code unit**, not synonymous with a Unicode code point. The **😄** emoji is two chars:

~~~text
U+1F604 (😄)
High surrogate: U+D83D
Low surrogate:  U+DE04
UTF-8 output:   F0 9F 98 84
~~~

If an input fragment ends at **U+D83D** and **endOfInput=false**, the encoder may return **UNDERFLOW** to wait for **U+DE04**. After **CharBuffer.compact()**, the high surrogate is preserved; providing the low surrogate next allows the encoder to produce valid bytes.

**Do not** encode each char fragment independently by creating a new encoder or calling **new String(chunk).getBytes(UTF_8)**. An isolated surrogate is treated as malformed or replaced, corrupting the byte stream.

On the output side, when the encoder writes bytes into a **ByteBuffer** and the program uses **SocketChannel.write(ByteBuffer)**:

- Call **output.flip()** and then write **while output.hasRemaining()**.
- If a non-blocking channel returns **0** or writes only partially, retain the unsent bytes; register **OP_WRITE** (when needed) and continue writing at the appropriate time.
- Only **clear()** output when **all bytes in it have been sent or copied out**.
- **OVERFLOW** from the encoder means you must consume output and then continue encoding unconsumed input, not drop bytes.
- Between input fragments, use **CharBuffer.compact()** to retain any unconsumed high surrogate or other code unit.

An application-layer **StringBuilder**/CharBuffer also needs bounds. If the producer is faster than the network link, you must apply **backpressure** rather than creating an unbounded byte queue.

## 7. endOfInput and flush(): Properly Ending a Session

Correct sequence at the end of a charset stream:

~~~text
Non-final fragments:
    decode(in, out, false) or encode(in, out, false)
    + drain output + compact input to receive more

Final fragment:
    decode(in, out, true) or encode(in, out, true)
    + handle OVERFLOW by draining output and retrying with endOfInput=true
    + on error: handle REPORT/REPLACE/IGNORE
    + on UNDERFLOW: main conversion phase is complete

Afterward:
    decoder.flush(out) or encoder.flush(out)
    + handle OVERFLOW until UNDERFLOW
    + drain remaining output

To process a new independent text:
    reset() or create a new encoder/decoder
~~~

**endOfInput=true** is an assertion that no further bytes/chars will follow in the **current charset session**—**not** "this is the end of the current read call" or "the TCP receive queue is temporarily empty".

If the final byte is an incomplete UTF-8 prefix, such as **C3** without a continuation byte, the decoder may return:

~~~text
decode([C3], endOfInput=false) → UNDERFLOW
decode([C3], endOfInput=true)  → MALFORMED[1] (with REPORT)
~~~

At EOF, **do not ignore leftover input**. If endOfInput=true has been signaled and malformed data is detected, apply the configured error policy (usually fail-fast in protocols). **flush(...)** is only valid after passing through the final decode/encode call with **endOfInput=true** and reaching **UNDERFLOW**; calling flush prematurely can throw **IllegalStateException** because the converter is not in the right state.

With completely empty input, you still need to transition the converter from its initial state through **decode/encode(empty, out, true)** before calling **flush**, rather than calling flush immediately. For some stateful charsets (such as encodings using shift sequences), flush may emit additional output, so it must not be skipped. For regular UTF-8, flush usually emits no extra bytes/chars, but the loop structure must still be correct.

Once a session has ended, **do not** continue calling decode(...,false)/encode(...,false) on the same converter before calling **reset()**.

## 8. Complete Java 17+ Program: Decoding and Encoding One Code Unit at a Time

A self-verifying demo **requiring no network**: it simulates a source feeding UTF-8 bytes **one byte at a time**, and then simulates a source feeding **one UTF-16 char at a time**. This is a very harsh condition to test retaining **UTF-8 multibyte prefixes** and **UTF-16 high surrogates** across turns.

Code highlights:

- Decoder uses **ByteBuffer capacity 8** and **CharBuffer capacity 2**.
- Encoder uses **CharBuffer capacity 4** and **ByteBuffer capacity 4**.
- After each decode/encode, output is **flip → drain → clear**; input is **compact**ed to retain unconsumed data.
- Only the final fragment uses **endOfInput=true**, followed by a **flush** loop.
- Configured with **REPORT**, meaning charset errors are not silently replaced.
- Result is compared against the original UTF-8 bytes using **Arrays.equals**.

Create the file **StreamingCharsetDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.*;
import java.util.Arrays;
import java.util.HexFormat;

public class StreamingCharsetDemo {
    private static void drainChars(CharBuffer buffer, StringBuilder result) {
        buffer.flip();
        result.append(buffer);
        buffer.clear();
    }

    private static void drainBytes(ByteBuffer buffer, ByteArrayOutputStream result) {
        buffer.flip();
        while (buffer.hasRemaining()) {
            result.write(buffer.get());
        }
        buffer.clear();
    }

    static String decodeFragments(byte[] bytes) throws CharacterCodingException {
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        ByteBuffer input = ByteBuffer.allocate(8);
        CharBuffer output = CharBuffer.allocate(2);
        StringBuilder text = new StringBuilder();

        for (int i = 0; i < bytes.length; i++) {
            input.put(bytes[i]);
            input.flip();
            boolean lastFragment = (i == bytes.length - 1);

            while (true) {
                CoderResult status = decoder.decode(input, output, lastFragment);
                drainChars(output, text);
                if (status.isError()) {
                    status.throwException();
                }
                if (status.isOverflow()) {
                    continue;
                }
                if (status.isUnderflow()) {
                    break;
                }
            }
            input.compact();
        }
        while (true) {
            CoderResult status = decoder.flush(output);
            drainChars(output, text);
            if (status.isError()) {
                status.throwException();
            }
            if (status.isUnderflow()) {
                break;
            }
        }
        return text.toString();
    }

    static byte[] encodeFragments(String text) throws CharacterCodingException {
        CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        CharBuffer input = CharBuffer.allocate(4);
        ByteBuffer output = ByteBuffer.allocate(4);
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        char[] units = text.toCharArray();

        for (int i = 0; i < units.length; i++) {
            input.put(units[i]);
            input.flip();
            boolean lastFragment = (i == units.length - 1);

            while (true) {
                CoderResult status = encoder.encode(input, output, lastFragment);
                drainBytes(output, bytes);
                if (status.isError()) {
                    status.throwException();
                }
                if (status.isOverflow()) {
                    continue;
                }
                if (status.isUnderflow()) {
                    break;
                }
            }
            input.compact();
        }
        while (true) {
            CoderResult status = encoder.flush(output);
            drainBytes(output, bytes);
            if (status.isError()) {
                status.throwException();
            }
            if (status.isUnderflow()) {
                break;
            }
        }
        return bytes.toByteArray();
    }

    public static void main(String[] args) throws Exception {
        String input = "A€😄Z";
        byte[] raw = input.getBytes(StandardCharsets.UTF_8);
        String decoded = decodeFragments(raw);
        byte[] encoded = encodeFragments(input);

        System.out.println("inputHex=" + HexFormat.of().formatHex(raw));
        System.out.println("decoded=" + decoded);
        System.out.println("utf16Units=" + input.length());
        System.out.println("encodedHex=" + HexFormat.of().formatHex(encoded));
        System.out.println("sameBytes=" + Arrays.equals(raw, encoded));

        CharsetDecoder incomplete = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT);
        ByteBuffer oneByte = ByteBuffer.wrap(new byte[] {(byte) 0xC3});
        CharBuffer chars = CharBuffer.allocate(4);
        System.out.println("beforeEOF=" + incomplete.decode(oneByte, chars, false));
        System.out.println("atEOF=" + incomplete.decode(oneByte, chars, true));

        CharsetEncoder ascii = StandardCharsets.US_ASCII.newEncoder()
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        System.out.println("asciiEuro=" +
                ascii.encode(CharBuffer.wrap("€"), ByteBuffer.allocate(8), true));
    }
}
~~~

Compile and run with JDK 17+ in the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 StreamingCharsetDemo.java
java StreamingCharsetDemo
~~~

**Stdout from a successful run** (verified with JDK 24, compiled targeting Java 17):

~~~text
inputHex=41e282acf09f98845a
decoded=A€😄Z
utf16Units=5
encodedHex=41e282acf09f98845a
sameBytes=true
beforeEOF=UNDERFLOW
atEOF=MALFORMED[1]
asciiEuro=UNMAPPABLE[1]
~~~

### Part-by-Part Analysis

**Decoder:**

1. Takes each byte from the **raw** array and calls **input.put(...)** while ByteBuffer is in write mode.
2. **flip()** lets the decoder read the new byte plus any UTF-8 prefix bytes retained from before.
3. **decode(..., false)** on non-final fragments may leave bytes that are not yet enough to form a character. **compact()** retains those bytes; the next turn appends after them.
4. **CharBuffer capacity 2** is enough to hold a supplementary Unicode code point as a surrogate pair.
5. Once the final byte is received, **decode(..., true)** ends the stream, followed by **flush**.
6. The result is **A€😄Z** without losing code points whose bytes were split.

**Encoder:**

1. **text.toCharArray()** produces 5 UTF-16 code units: **A**, **€**, high surrogate, low surrogate, **Z**.
2. Feeding **one char** at a time, **encode(..., false)** may need to wait for the low surrogate. **CharBuffer.compact()** retains the remaining high surrogate between calls.
3. Output **ByteBuffer capacity 4** is enough to write one UTF-8 code point of up to 4 bytes; the loop still properly structures **OVERFLOW** handling and **flush**.
4. **sameBytes=true** means the demo reproduces the exact original byte array for the chosen input, not a guarantee that every charset or input round-trips when errors or normalization occur.

**Demonstrated errors:**

- **beforeEOF=UNDERFLOW**: byte **C3** is the start of a UTF-8 sequence that may need more bytes.
- **atEOF=MALFORMED[1]**: if the stream actually ends at byte **C3**, that byte becomes incomplete UTF-8 data.
- **asciiEuro=UNMAPPABLE[1]**: **€** is a valid Unicode character, but the **US-ASCII** charset cannot encode it.

**Demo limitations:** **decodeFragments/encodeFragments** accept **non-empty** strings/arrays to simplify the loop. In a general implementation, **empty input** must be handled by a final **endOfInput=true** decode/encode call before flush. In real network applications, read bytes from the channel, manage unwritten output buffers, and enforce resource limits; do not create unbounded ByteArrayOutputStream/StringBuilder instances for untrusted data.

## 9. REPORT, REPLACE, or IGNORE: Choosing an Error Policy Deliberately

There are two key error types:

- **Malformed input**: byte sequences or UTF-16 code units that are **invalid** for the encoding. For example, UTF-8 ending with byte **C3**, or encoder input containing an isolated high surrogate.
- **Unmappable character**: valid input, but **the target charset has no representation for it**. For example, **€** with a **US_ASCII CharsetEncoder**.

Configuration:

~~~java
CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetDecoder tolerant = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .onUnmappableCharacter(CodingErrorAction.REPLACE)
        .replaceWith("\uFFFD");

CharsetEncoder ascii = StandardCharsets.US_ASCII.newEncoder()
        .onUnmappableCharacter(CodingErrorAction.REPLACE);
// A valid replacement byte[] can be configured via ascii.replaceWith(...).
~~~

The above is a **configuration snippet**. Policies:

| Action | Behavior | Risk / Use Case |
| --- | --- | --- |
| **REPORT** | Returns an error CoderResult; caller decides to throw an exception, close the frame, or close the connection | Suitable for protocols requiring integrity |
| **REPLACE** | Replaces invalid data with a configured replacement | Useful for "best effort" display, but may lose information |
| **IGNORE** | Drops invalid data and continues | May silently delete important bytes/chars; usually unsuitable for security-sensitive data |

**CharsetDecoder** typically uses the **U+FFFD** replacement character, while **CharsetEncoder** uses a valid replacement **byte[]** for the target charset. Do not equate the behavior of **new String(byte[], charset)** or **String.getBytes(charset)** (convenience APIs that use replacement policies on invalid data) with an encoder/decoder configured with **REPORT**. Always define the protocol rules.

Security scenario: if one layer uses **REPLACE/IGNORE** to sanitize invalid data while another layer interprets the raw bytes differently, the layers may **disagree on the message content**. For protocols requiring strict syntax, use a fixed charset (usually UTF-8), **REPORT**, size limits, and post-decode content validation.

## 10. Combining with SocketChannel: Byte, Text, and Message Boundaries

A proper networking pipeline separates at least three concerns:

~~~text
TCP byte stream
    ↓ SocketChannel.read()
ByteBuffer accumulating bytes (may contain half a character)
    ↓ stateful CharsetDecoder
CharBuffer / Unicode character sequence
    ↓ protocol parser
Complete message (delimiter, length-prefix, JSON stream, ...)
    ↓ validation and business logic
~~~

**CharsetDecoder only solves assembling bytes into characters**; it does not tell you "a full HTTP request has been read", "end-of-line was reached", or "a JSON document was received". Parsing messages requires **framing**: byte length, an appropriate delimiter, or a streaming parser. With length-prefixed UTF-8 protocols, you must read the full **byte** count first (or streaming-decode within the exact frame boundary); do not confuse **byte length** with **String.length()**, because String.length() counts UTF-16 code units.

### Sketch of a Channel Receive Loop

~~~java
// Illustrative pseudocode, not a standalone program:
// channel is a SocketChannel; decoder and buffers belong exclusively to the connection.
int n = channel.read(inputBytes); // Input ByteBuffer is in write mode.
if (n == -1) {
    inputBytes.flip();
    // Call decoder.decode(..., true) in a loop,
    // handle CoderResult, drain CharBuffer, and call decoder.flush(...).
} else if (n > 0) {
    inputBytes.flip();
    // Call decoder.decode(..., false), handle OVERFLOW / ERROR.
    // After UNDERFLOW: inputBytes.compact() to retain incomplete bytes.
} else {
    // n == 0: not EOF; wait for the next read.
}
~~~

This snippet illustrates **state structure** and does not implement the decode loop, output draining, error handling, or selector; do not copy it as a runnable server. The **StreamingCharsetDemo** program in Section 8 is the runnable, verified example for the core algorithm.

### Sketch of a Non-Blocking Channel Send Loop

~~~java
// Pseudocode, not standalone:
// outputBytes has been written into by the encoder in write mode.
outputBytes.flip();
while (outputBytes.hasRemaining()) {
    int n = channel.write(outputBytes);
    if (n == 0) {
        // Do not clear outputBytes!
        // Keep the remaining bytes, wait for OP_WRITE, and continue.
        break;
    }
}
// Only clear() or reuse after all bytes have actually left the buffer.
// If bytes remain, keep read mode for the next write.
~~~

Data returned by **encoder** is not synonymous with data sent to the peer: **SocketChannel.write** may perform partial writes. Even when write consumes the entire ByteBuffer, the TCP layer has only accepted the bytes for transport; only a protocol response tells you the peer has processed the request.

### When to Reset the Encoder/Decoder?

A **connection** may carry multiple messages. There are two different designs:

- **Continuous encoded text stream**: keep the same decoder across all reads and messages, passing endOfInput=true only when the stream truly ends; a separate parser extracts messages from the char stream.
- **Independent frames, each containing a complete text encoding**: you may create a new decoder (or reset after flush) for **each frame**; you must guarantee that the frame ends on a valid byte boundary and does not contain half a character from the next frame.

For stateful charsets, creating/resetting a decoder at the wrong boundary can lose shift/escape state. For UTF-8, reinitializing on every read is still wrong if a code point is split; only scope sessions to protocol-confirmed text boundaries.

## 11. Buffer Sizing, Performance, and Real-World Data

**ByteBuffer.allocateDirect(...)** can be useful in certain high-throughput I/O paths, but it is not "enable direct and it is always faster" for every workload. Direct buffers have management overhead and require real benchmarking. CharsetDecoder/Encoder work with **ByteBuffer/CharBuffer**; choose heap/direct based on the workflow and buffer retention/reuse strategy.

**Output size can differ from input size**:

- UTF-8 → UTF-16 can turn a 4-byte code point into **2 chars**.
- UTF-16 → UTF-8 can turn one char into 1–3 bytes or a surrogate pair into 4 bytes.
- Do not use **bytes.length == text.length()** as a memory formula; **String.length()** counts UTF-16 code units, not Unicode code points and not visible characters (grapheme clusters).
- **CharsetDecoder.averageCharsPerByte() / maxCharsPerByte()** and **CharsetEncoder.averageBytesPerChar() / maxBytesPerChar()** are only sizing hints; overflow handling is still required because charset, state, and replacements can change the actual element count.

### Four Performance Principles

1. **Reuse** buffers and decoder/encoder within **a single session** instead of allocating per packet. **Do not** share a stateful instance concurrently across connections/threads.
2. **Separate protocol limits from buffer capacity**: an 8 KiB ByteBuffer does not mean a max 8 KiB message. Track total processed bytes/chars to prevent memory exhaustion and oversized messages.
3. **Measure backpressure**: if a downstream parser is slow or a non-blocking channel has not finished writing, do not push data into an unbounded queue; pause reading or throttle the producer appropriately.
4. **Choose charsets explicitly**: **StandardCharsets.UTF_8** for UTF-8 protocols; do not rely on the platform default charset. With stateful charsets like ISO-2022-JP, preserving state and calling **flush** at the right time is even more critical.

### BOM, Normalization, and Unicode Boundaries

A UTF-8 stream may begin with the BOM bytes **EF BB BF**. How the decoder or application layer handles **U+FEFF** must follow the protocol/format specification; do not blindly strip every U+FEFF from content. CharsetDecoder **does not** perform Unicode normalization (NFC/NFD), does not check semantic validity of an entire JSON/XML/HTTP message, and does not guarantee text is valid for a business field. If character restrictions or Unicode confusables need handling, downstream validation must be designed separately.

## 12. Common Bugs and Fixes

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| **�** character appears when UTF-8 bytes split across read boundaries | Creating String from each byte chunk or enabling REPLACE without keeping leftover bytes | Keep **CharsetDecoder** across fragments, **ByteBuffer.compact()** |
| Emoji lost or turns into **?** when encoding char by char | Splitting surrogate pair and encoding independently | Retain high surrogate with **CharBuffer.compact()**, encode as a stream |
| 100% CPU in decode loop | Received OVERFLOW without draining output; or output too small to make progress | Drain output; ensure sufficient capacity and check progress |
| Exception after calling flush | Did not call decode/encode with **endOfInput=true** and reach UNDERFLOW | Follow the state machine |
| Data read is missing the final character | Ended without decode(..., true) / flush; or discarded leftover bytes | Handle EOF properly, REPORT truncated sequences |
| Bytes remain in input, but next read produces garbled text | Used **clear()** instead of **compact()** on unconsumed input | Preserve remaining prefix properly |
| Lost sent bytes on non-blocking SocketChannel | Cleared output when **write()** only wrote partially or returned **0** | Keep ByteBuffer with remaining bytes, wait for writable, and continue writing |
| Decoder throws MalformedInputException | Data contains invalid bytes/wrong charset or was truncated at EOF | Check wire bytes, declared charset, framing, and error policy |
| ASCII encoder reports Unmappable | String contains characters outside ASCII | Choose UTF-8 or handle REPORT/REPLACE per contract |
| Each read returns a merged or incomplete "message" | Confused TCP read boundary with message boundary | Add independent framing/parser after decode |
| Reusing decoder for another frame throws IllegalStateException | Instance is still in FLUSHED or ended state | **reset()** after flush or create a new instance |
| Small buffer repeatedly underflows with no room to read more | Buffer cannot hold one sequence or hit resource limit | Grow within bounds / adjust buffer sizing |

### Self-Check Checklist for Incremental Pipelines

- [ ] Is the charset explicitly specified and consistent on both sides?
- [ ] Is there **one encoder/decoder per independent encoding stream**, not recreated per packet?
- [ ] After **UNDERFLOW**, does input **compact()** retain unconsumed bytes/chars?
- [ ] After **OVERFLOW**, is output drained before retrying, even if the buffer is small?
- [ ] Is **read()==0** distinguished from **read()==-1**?
- [ ] Is **endOfInput=true** set only when the charset stream is truly complete?
- [ ] After final decode/encode, is **flush** called until UNDERFLOW?
- [ ] Is there an explicit **REPORT/REPLACE/IGNORE** policy handling malformed/unmappable input?
- [ ] When channel.write() has not written everything, are output bytes preserved?
- [ ] Are message framing, payload limits, and backpressure handled?
- [ ] Are multibyte UTF-8 characters and surrogate pairs tested when split at every position?
- [ ] Is the decoder reset/recreated when starting **a new independent session**?

## 13. Practice Exercises

1. Use the string **"Việt Nam 😄"** and test every way of splitting its UTF-8 bytes into chunks of length 1 to 5. Compare the result from **CharsetDecoder** with the original string; explain why decoding each chunk with **new String(...)** can fail.
2. Change **CharBuffer.allocate(2)** in the demo to **allocate(1)**. Observe the issue when encountering the emoji and fix the loop by increasing capacity enough for a surrogate pair; do not busy-loop forever.
3. Feed **E2 82** and then end the stream. Compare **decode(false)** and **decode(true)** with REPORT and REPLACE. Why do the results differ at the two points in time?
4. Pass **"A€B"** into **US_ASCII.newEncoder()**. Compare REPORT, REPLACE, and IGNORE, evaluating the risk of data loss when a protocol requires exact content.
5. Write a TCP client/server using **SocketChannel**: the server incrementally decodes UTF-8, a parser reads messages by **byte** length-prefix, and then encodes a UTF-8 response. Simulate reads returning only 1–2 bytes; add a test for EOF in the middle of a UTF-8 sequence.
6. With a non-blocking channel, simulate **write(ByteBuffer)** returning 0 or writing partially. Design state that retains the unsent output ByteBuffer and avoids unbounded queues.

**Summary:** **CharsetDecoder** converts **byte → char** and **CharsetEncoder** converts **char → byte** in **a stateful session**. **UNDERFLOW** requires retaining incomplete input; **OVERFLOW** requires draining output; **MALFORMED / UNMAPPABLE** require an error policy. Use **flip → decode/encode → drain output → compact input**, set **endOfInput=true** only at the true end of the stream, then **flush** and **reset** if starting a new stream. Charset conversion itself does not replace TCP framing, I/O timeouts, or application protocols.

**Official Documentation:** [CharsetDecoder (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html), [CharsetEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html), [CoderResult](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CoderResult.html), [ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html), [SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html).