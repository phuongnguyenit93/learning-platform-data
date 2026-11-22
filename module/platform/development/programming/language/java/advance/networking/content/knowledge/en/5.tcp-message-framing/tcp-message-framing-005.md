# UTF-8 Encoding and Handling Characters Split Across Multiple TCP Reads (Java 17+)

A TCP connection transfers a **byte stream**, not Unicode characters or “one `write()` equals one message.” UTF-8 represents a Unicode character using **1–4 bytes**. Therefore, a single `InputStream.read()` call can end right in the middle of a character's UTF-8 representation; the next read will contain the remaining bytes. If each received chunk is converted into a `String` independently, the application can turn valid data into the replacement character `�`, corrupting JSON, Vietnamese text, or messaging content.

This lesson explains two boundaries that must be handled independently:

- **TCP byte boundaries:** where `read()` calls happen to return; not guaranteed to align with `write()` calls, characters, or messages.
- **Unicode and application message boundaries:** the decoder must maintain state across byte chunks, while the protocol must determine a complete message before validating it.

The context belongs to **TCP Message Framing**. The examples use Java 17+ `Socket`/`ServerSocket` over loopback, requiring no Internet or external libraries.

## 1. How Does UTF-8 Represent Characters as Bytes?

Unicode identifies characters by **code point**; Java `String` stores data as **UTF-16 code units** (`char`). UTF-8 converts each Unicode scalar value into a sequence of 1 to 4 bytes. These three concepts are not interchangeable:

| Concept | Unit | Example |
| --- | --- | --- |
| `String.length()` | Number of UTF-16 code units | Non-BMP emojis typically take **2** `char`s |
| `String.codePointCount(0, s.length())` | Number of Unicode code points in the Java string | An emoji like `😀` is **1** code point |
| `s.getBytes(UTF_8).length` | Number of UTF-8 bytes after encoding | `😀` takes **4** bytes |
| `InputStream.read(...)` | Number of **bytes** read | Has no concept of “complete characters” |
| `Reader.read(...)` | Number of **UTF-16 `char`s** read | Can end between a **surrogate pair** of a non-BMP code point |

For the string `A€😀B`:

```text
Displayed character: A       €            😀                  B
Code point:          U+0041  U+20AC       U+1F600             U+0042
UTF-8 bytes (hex):   41      E2 82 AC     F0 9F 98 80        42

Total UTF-8: 9 bytes
Java String.length(): 5 chars (A=1, €=1, 😀=2, B=1)
Code point count: 4
```

The bytes `E2 82 AC` together represent the `€` character. The bytes `F0 9F 98 80` together represent the `😀` emoji. A TCP read boundary can easily fall at any position within these sequences.

**Warning:** a code point is not necessarily equivalent to a *grapheme cluster* (a user-perceived character). An accented letter can be represented by a precomposed code point or by a base letter + combining mark. Correct UTF-8 stream decoding still does not automatically perform Unicode normalization (NFC/NFD) or split grapheme clusters for display.

## 2. Why Can a Character Be Split Across Two `read()` Calls?

TCP preserves **byte order** in one direction of a connection, but does not preserve boundaries between `write()` calls. Two writes can be coalesced on receipt; one write can be split into multiple reads; a single read can return fewer bytes than the buffer size.

Suppose the sender has correctly encoded `A€😀B` into 9 bytes. The receiver happens to read it in three chunks:

```text
Read 1:       41 E2              ("A" and the first byte of "€")
Read 2:       82 AC F0 9F        (last 2 bytes of "€", first 2 bytes of "😀")
Read 3:       98 80 42           (last 2 bytes of "😀", "B")
Concatenated: 41 E2 82 AC F0 9F 98 80 42
Correct:      A  €        😀          B
```

No chunk in this example was “sent wrong” by TCP: the reassembled byte sequence is intact and in the right order. **The error occurs at the application layer** if each chunk is assumed to be a complete UTF-8 string.

Do not infer the number of bytes read from the number of bytes written via `write`, the UTF-8 byte count from `String.length()`, or a character-end threshold from `InputStream.available()`.

## 3. Common Mistake: `new String(chunk, UTF_8)` in Every Read Loop

The following snippet is **incomplete illustrative code** (assuming `in` is a connected `InputStream`):

```java
byte[] buffer = new byte[4096];
int count;
StringBuilder text = new StringBuilder();

while ((count = in.read(buffer)) != -1) {
    // WRONG when UTF-8 bytes of a character are split across two read() calls:
    text.append(new String(
            buffer, 0, count, StandardCharsets.UTF_8));
}
```

Each call to `new String(byte[], off, len, charset)` interprets **a set of bytes as a complete decoding unit**. If a chunk ends with the prefix of a UTF-8 character missing trailing bytes, the decoder in that call does not retain the incomplete portion for the next call. With many standard String decoding APIs, malformed data is **replaced with the replacement character U+FFFD**; thus the final message is corrupted even though all TCP bytes arrived.

```text
Chunk 1: 41 E2         -> "A�"       (E2 is missing 82 AC)
Chunk 2: 82 AC F0 9F   -> "��..."    (starts with continuation bytes)
Chunk 3: 98 80 42      -> "��B"
Concatenating these strings cannot recover "A€😀B".
```

The exact number of `�` characters can depend on the decoder and how the data was split. What must be emphasized is that **decoding each chunk independently does not preserve characters split across chunks**.

Even if the text looks right in a test environment, that may only be because the receive timing happened to align with UTF-8 boundaries. Changing buffer sizes, network load, proxies, or CPU scheduling can cause the bug to surface.

## 4. Approach 1: Use `InputStreamReader` for Continuous Decoding

`InputStreamReader` bridges a byte stream to a character stream. It uses a continuous decoder across reads; UTF-8 bytes that do not yet form a complete character can be retained to combine with the next incoming bytes. This is a convenient choice when **the entire stream** is UTF-8 text and you have a rule to determine the end of the stream/message.

```java
// Illustrative snippet (in is an InputStream, not a standalone class).
try (Reader reader =
             new InputStreamReader(in, StandardCharsets.UTF_8)) {
    char[] chars = new char[2048];
    int n;
    while ((n = reader.read(chars)) != -1) {
        // Only use chars[0..n), which may contain part of a surrogate pair.
        processChars(chars, n);
    }
}
```

`processChars` in this snippet is an application-defined method, not a built-in Java API. **Do not immediately treat each `Reader.read` call as a complete message.** `Reader` resolves boundaries between UTF-8 bytes, but a `char[]` read can still split a *surrogate pair* across two `char` chunks: if processing by code point is required, you must retain an incomplete surrogate or assemble the full string and iterate with `codePoints()`.

The illustrative example uses `try-with-resources` because the input is treated as a **complete stream ending with EOF**. On a TCP connection kept open to exchange multiple messages, EOF should not be used as the end condition for individual messages; you need protocol framing as covered below. Also, do not close the `Reader` if you still need to use the socket: closing a reader that owns the stream can close the underlying stream/socket.

## 5. Runnable Java 17+ Example: Receiving UTF-8 Split Mid-Character

The file **`Utf8SplitTcp.java`** creates a loopback socket pair. The sender writes 9 bytes in three parts, right at the positions that split `€` and `😀`. The receiver uses a wrapper that intentionally limits each `InputStream.read(byte[], off, len)` operation to at most **1 byte**, forcing the decoder to frequently wait for the next byte.

```java
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class Utf8SplitTcp {
    public static void main(String[] args) throws Exception {
        String expected = "A\u20AC\uD83D\uDE00B";
        byte[] utf8 = expected.getBytes(StandardCharsets.UTF_8);

        String broken =
                new String(utf8, 0, 2, StandardCharsets.UTF_8)
                + new String(utf8, 2, 4, StandardCharsets.UTF_8)
                + new String(utf8, 6, 3, StandardCharsets.UTF_8);

        try (ServerSocket listener = new ServerSocket(
                     0, 1, InetAddress.getLoopbackAddress());
             Socket sender = new Socket(
                     InetAddress.getLoopbackAddress(), listener.getLocalPort());
             Socket receiver = listener.accept()) {

            OutputStream output = sender.getOutputStream();
            output.write(utf8, 0, 2);
            output.write(utf8, 2, 4);
            output.write(utf8, 6, 3);
            sender.shutdownOutput();

            InputStream oneBytePerRead =
                    new FilterInputStream(receiver.getInputStream()) {
                        @Override
                        public int read(byte[] b, int off, int len)
                                throws IOException {
                            return super.read(b, off, Math.min(len, 1));
                        }
                    };

            InputStreamReader decoder = new InputStreamReader(
                    oneBytePerRead, StandardCharsets.UTF_8);
            StringBuilder decoded = new StringBuilder();
            char[] chars = new char[2];
            int n;
            while ((n = decoder.read(chars)) != -1) {
                decoded.append(chars, 0, n);
            }

            System.out.println("UTF-8 bytes: " + utf8.length);
            System.out.println("Java char units: " + expected.length());
            System.out.println("Unicode code points: "
                    + expected.codePointCount(0, expected.length()));
            System.out.println("Decode each chunk correct: "
                    + expected.equals(broken));
            System.out.println("Streaming decode correct: "
                    + expected.contentEquals(decoded));
        }
    }
}
```

Run with JDK 17+:

```sh
javac -encoding UTF-8 Utf8SplitTcp.java
java Utf8SplitTcp
```

Deterministic stdout:

```text
UTF-8 bytes: 9
Java char units: 5
Unicode code points: 4
Decode each chunk correct: false
Streaming decode correct: true
```

Explanation:

1. `broken` decodes three `byte[]` slices **independently**, so it cannot reconstruct the original string.
2. `InputStreamReader` maintains state across byte reads; the code uses a single decoder for the entire stream, then appends the decoded `char`s in order.
3. The program prints **Boolean true/false** instead of relying on terminal support for displaying emojis and Vietnamese characters.
4. `write` calls do not guarantee matching `read` boundaries. The one-byte-per-read wrapper is an intentional test for a harsh scenario, **not a claim that real TCP always delivers 1 byte at a time**.

The example only sends one payload and then calls `shutdownOutput()` so the receiver can read until EOF. This approach is suitable for a demo, **not sufficient as a multi-message protocol** where both sides must keep the socket open.

## 6. Approach 2: When Message Boundaries Exist, Assemble the **Exact Bytes** Before Decoding

If an application transmits independent messages over the same connection, it needs a **framing** protocol such as **length-prefix** or a delimiter with escaping/limits. With length-prefix:

```text
+-------------------------+-----------------------------------+
| Header: 4-byte length N | Body: exactly N UTF-8 bytes       |
+-------------------------+-----------------------------------+
  readInt()                readFully(byte[N]) -> UTF-8 decode once
```

Safe receiving flow:

1. Read the full header in the exact format: `DataInputStream.readInt()` reads a 32-bit big-endian integer, matching `DataOutputStream.writeInt()`.
2. Validate `0 <= N <= MAX_FRAME_BYTES` according to application policy **before allocating**.
3. `readFully(payload)` reads **exactly N bytes** across however many TCP reads it takes, or throws `EOFException` if the stream ends while the frame is incomplete.
4. Only when the body is complete, perform `UTF-8` decoding. For untrusted data, use `CharsetDecoder` in `REPORT` mode to reject malformed UTF-8 bytes rather than silently replacing them with `�`.
5. Repeat for the next frame. Framing solves **message boundaries**, while the decoder solves **Unicode boundaries**.

**The header length must be the number of UTF-8 bytes**, not `String.length()` or the code point count. For example, `"Xin chào"` has 8 UTF-16 code units but 9 UTF-8 bytes, because `à` takes 2 bytes.

Both sides of the protocol must agree on the integer type, byte order, maximum size, frame count, and how EOF is handled. TCP does not provide these conventions on behalf of the application.

## 7. Runnable Java 17+ Example: 2 UTF-8 Frames and Malformed Byte Check

The file **`Utf8FramedMessages.java`** sends two messages over a loopback TCP connection using the same 4-byte length-prefix format. The receiver caps the body at 1024 bytes, reads the entire frame, and uses a strict `CharsetDecoder`. After two frames, the sender half-closes its output; the client reads and confirms EOF. The program also intentionally tests a UTF-8 sequence missing its last byte to verify that the strict decoder reports an error.

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class Utf8FramedMessages {
    private static final int MAX_FRAME_BYTES = 1024;

    private static void writeFrame(DataOutputStream out, String message)
            throws IOException {
        byte[] payload = message.getBytes(StandardCharsets.UTF_8);
        if (payload.length > MAX_FRAME_BYTES) {
            throw new IOException("Frame too large");
        }
        out.writeInt(payload.length);
        out.write(payload);
    }

    private static String strictDecode(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    private static String readFrame(DataInputStream in) throws IOException {
        int length = in.readInt();
        if (length < 0 || length > MAX_FRAME_BYTES) {
            throw new IOException("Invalid frame length: " + length);
        }
        byte[] payload = new byte[length];
        in.readFully(payload);
        return strictDecode(payload);
    }

    public static void main(String[] args) throws Exception {
        String first = "Xin chào";
        String second = "\uD83D\uDE00: OK";

        try (ServerSocket listener = new ServerSocket(
                     0, 1, InetAddress.getLoopbackAddress());
             Socket sender = new Socket(
                     InetAddress.getLoopbackAddress(), listener.getLocalPort());
             Socket receiver = listener.accept()) {

            sender.setSoTimeout(5000);
            receiver.setSoTimeout(5000);

            DataOutputStream out =
                    new DataOutputStream(sender.getOutputStream());
            writeFrame(out, first);
            writeFrame(out, second);
            out.flush();
            sender.shutdownOutput();

            DataInputStream in =
                    new DataInputStream(receiver.getInputStream());
            String received1 = readFrame(in);
            String received2 = readFrame(in);

            System.out.println("Frames: 2");
            System.out.println("First UTF-8 bytes: "
                    + first.getBytes(StandardCharsets.UTF_8).length);
            System.out.println("Payloads match: "
                    + (first.equals(received1) && second.equals(received2)));
            System.out.println("EOF after frames: " + (in.read() == -1));
        }

        byte[] truncated = {(byte) 0xE2, (byte) 0x82};
        try {
            strictDecode(truncated);
            System.out.println("Truncated rejected: false");
        } catch (CharacterCodingException expected) {
            System.out.println("Truncated rejected: true");
        }
    }
}
```

Run:

```sh
javac -encoding UTF-8 Utf8FramedMessages.java
java Utf8FramedMessages
```

Deterministic stdout on a normal run:

```text
Frames: 2
First UTF-8 bytes: 9
Payloads match: true
EOF after frames: true
Truncated rejected: true
```

Notes:

- `writeFrame` sends **a 4-byte header followed by the entire body**. There is no requirement for TCP to deliver each frame in a single read.
- `readFully` handles the case where the body is split across multiple receives. If the connection closes mid-frame, an exception is thrown instead of returning a truncated message.
- `strictDecode` uses `CodingErrorAction.REPORT`; the two-byte sequence `E2 82` lacks the final byte of the three-byte character, so it is **rejected** when treated as a complete message.
- `setSoTimeout(5000)` sets the timeout for a single blocking socket read operation, not guaranteeing that the total end-to-end time across multiple reads is 5 seconds.
- `shutdownOutput()` closes the sending direction after the frames; it is **not** a message terminator for all protocols and carries no semantics of “business logic processed successfully.”

The example sends valid Java `String` values. If the character source contains an **unpaired surrogate** (malformed UTF-16), ordinary `String.getBytes(UTF_8)` may replace the input data; to **reject invalid input right on the sending side**, use `CharsetEncoder` with `onMalformedInput(REPORT)` and handle `CharacterCodingException` before sending. Strict decoding on the receiving side **cannot recover** characters that were already replaced on the sending side.

## 8. Incremental Decoding with `CharsetDecoder` for Complex Stream Handling

`InputStreamReader` is suitable for most text streams. When using NIO/`SocketChannel`, wanting control over buffers, error states, non-blocking I/O, or incrementally decoding byte fragments from a custom parser, use **a single** `CharsetDecoder` throughout the logic flow.

A stateful decoder can encounter three results:

| `CoderResult` | Meaning | Appropriate Response |
| --- | --- | --- |
| `UNDERFLOW` | All available bytes consumed **or** a UTF-8 prefix is waiting for more bytes | Keep unconsumed bytes; fetch more bytes without resetting the decoder |
| `OVERFLOW` | Output `CharBuffer` is full | Drain/process decoded characters and free space, then continue decoding |
| Error (`malformed`/`unmappable`) | Invalid data per `CodingErrorAction.REPORT` | Reject the frame/stream according to protocol policy |

Buffer rules in a continuous decoder loop:

```text
1. Load new bytes into ByteBuffer in WRITE mode.
2. flip(): switch to READ mode.
3. decoder.decode(input, output, endOfInput=false).
4. Process output chars and handle OVERFLOW if any.
5. input.compact(): keep the bytes NOT YET consumed by the decoder.
6. Wait for the next bytes, repeat.
7. Only when the stream/frame truly ends: decode(..., true), then flush(output).
```

**`compact()` is critical:** it shifts unconsumed bytes to the beginning of the buffer instead of discarding an incomplete UTF-8 sequence. If you call `clear()` when the decoder has not consumed all bytes, characters are lost. If you call `decode(..., true)` at the end of **every** `Socket.read()`, the decoder will treat a pending UTF-8 prefix as *end of stream* and may falsely report malformed input.

For length-prefixed messages where **all bytes are already available**, decoding once with `CharsetDecoder.decode(ByteBuffer.wrap(payload))` is usually simpler and safer than writing a custom buffering loop. Do not add a state machine when `InputStreamReader` or `readFully` satisfies the protocol.

## 9. In What Order Should Encoding and Framing Be Applied?

**Sending side:** construct the logical message → validate/normalize content per convention → UTF-8 encode to bytes → compute `payload.length` → send header → send body.

**Receiving side:** read frame header at the byte level → read exact body at the byte level → UTF-8 decode (strict if needed) → parse text/JSON data → validate content → execute business logic.

Diagram:

```text
Sender:
String ──UTF-8 encode──> byte[] ──length prefix──> TCP byte stream

Receiver:
TCP byte stream ──read length──> N bytes ──UTF-8 decode──> String
                                      └── Early EOF? -> malformed frame
                                      └── Invalid UTF-8? -> reject frame
```

A real-world bug is using an `InputStreamReader`/`BufferedReader` to read a text header, then switching back to `Socket.getInputStream()` to read a binary body on the same connection. The reader may **read ahead** extra bytes from the underlying stream to buffer/decode, leaving body bytes inside the reader's buffer instead of where raw input code expects them. Therefore, you need **one consistent parser** for the entire wire format, or a buffering layer designed for valid sharing.

If the protocol is truly **text-delimited** such as LF-terminated lines, you can use `BufferedReader.readLine()` over a UTF-8 `InputStreamReader`. However, you must bound line length, define escaping/delimiters, and specify how to handle lines ending without LF; `readLine()` has no built-in length limit and can block indefinitely if the peer never sends a newline.

## 10. End of Stream, Truncated Frames, and UTF-8 Errors: Distinguishing Three Scenarios

**Scenario A: TCP splits a character, but more bytes are still coming.** Incomplete UTF-8 bytes at the end of a `read` are **normal**. A stateful decoder waits for the next bytes; do not flag this prefix as an error.

**Scenario B: A frame declares N bytes, but fewer than N bytes arrive before EOF.** This is a **truncated frame**. `readFully` throws `EOFException`. Do not interpret incomplete data as a valid message, even if the bytes read so far can be decoded into a string.

**Scenario C: A frame has all N bytes, but the UTF-8 body is malformed or ends with an incomplete prefix.** This is a **message encoding error**. A strict decoder reports an error; a replacement decoder can produce `�` and mask the fact that the input data was invalid.

EOF from `InputStream.read()` is `-1` **after all data has been read** and the sending side has closed normally. When the peer resets or the connection fails, you may receive an `IOException` instead of EOF. **A timeout is not EOF**: `SocketTimeoutException` indicates no progress within the read operation's wait window; it does not prove the message is complete or that the peer aborted it.

In production, you must clearly specify when to close the connection after a malformed frame, whether to return an application error code, and whether that message is allowed to be retried.

## 11. Non-BMP Unicode, Surrogate Pairs, and Accented Characters

UTF-8 represents a Unicode scalar value in 1–4 bytes; a Java `char` is a 16-bit UTF-16 unit. For example, the emoji `😀`:

```text
Unicode code point: U+1F600
UTF-8:  F0 9F 98 80          (4 bytes)
UTF-16: D83D DE00            (2 Java chars / surrogate pair)
```

Even after correct UTF-8 decoding, `Reader.read(char[])` can return a `char` chunk containing a **high surrogate** whose low surrogate arrives in the next read. If you append the `char`s in order and use the full `String`, the surrogate pair will be combined properly. However, if the application converts **each `char[]` chunk** to JSON, checks “every char is a character,” or counts emojis with `String.length()`, boundary bugs still occur.

To iterate code points once you have the complete message:

```java
// Illustrative, not a standalone program.
String message = "A\u20AC\uD83D\uDE00B";
long count = message.codePoints().count(); // 4 code points
message.codePoints().forEach(cp -> {
    // Each cp represents one Unicode code point (int).
});
```

`String.codePoints()` handles valid surrogate pairs in a string; the fact that visually identical text can have different code points (NFC/NFD) remains a separate Unicode normalization issue, **not a TCP split-read bug**. If the protocol requires normalization for identifier comparison, the normalization policy and security implications must be agreed upon.

## 12. Choosing a Handling Mechanism by Application Type

| Protocol / Requirement | Preferred Handling Approach | Notes |
| --- | --- | --- |
| Single UTF-8 text stream ending on peer half-close | One `InputStreamReader` across the entire stream | Read until EOF; bound total length/duration |
| Multiple messages on one TCP connection | Length-prefix or delimiter framing first | Do not use `read` count to measure messages |
| Length-prefix containing a UTF-8 body | `DataInputStream.readFully` + `CharsetDecoder` per **complete frame** | Cap byte length, use strict decoding if needed |
| NIO, asynchronous streams, complex binary/text parsers | Stateful `CharsetDecoder` with `ByteBuffer.compact` | Do not reset or set `endOfInput=true` between chunks |
| LF-delimited UTF-8 lines | `BufferedReader` + line limit at protocol/parser | `readLine` can read-ahead and has no length limit |
| UTF-8 data that may contain malformed bytes | `CodingErrorAction.REPORT` | Define error reporting and drop policy |
| Interactive protocol keeping the socket open | Framing with an EOF-independent end marker | Per-message timeouts and backpressure |

A protocol that simply “reads until EOF and then decodes” is only valid when **EOF itself is the defined data terminator**; if the peer keeps the socket open waiting for a response, a reader waiting for EOF can cause an application deadlock.

## 13. Common Pitfalls When Debugging Vietnamese Text Issues Over TCP

1. **“TCP dropped half of a Vietnamese character.”** If all bytes eventually arrive, TCP did not drop the character: the application is decoding each chunk separately or discarding trailing incomplete bytes.
2. **“A single `read(buffer)` should hold the whole message.”** False; `read` returns whatever bytes are currently available, which can be very few. Perform framing before parsing.
3. **“`new String(buffer, UTF_8)` processes the whole buffer.”** It can read **stale bytes** in the region not overwritten by the current read. Always use `buffer, 0, n`; however, even with `n` it is still **wrong** if decoding each chunk independently.
4. **“Sending length using `String.length()`.”** Wrong if the header describes UTF-8 byte length; with accents or emojis, the byte count differs from the `char` count.
5. **“`new String` didn't throw an error, so the bytes are valid.”** False: the default decoder may use the replacement character U+FFFD. Use a strict decoder if malformed data must be rejected.
6. **“EOF mid-character is the same as EOF after a message.”** False: EOF mid-frame or mid-UTF-8 sequence can mean a corrupted message; separate EOF, framing, and charset errors.
7. **“`Reader` always returns whole code points.”** False: the API reads `char`s and can split a surrogate pair; applications processing by code point must retain the pair.
8. **“Using UTF-8 on both sides is enough.”** Not yet: both sides must also agree on **framing, payload structure, header byte order, size limits, and error rules**.
9. **“`available() == 0` means end of message.”** False; it is not a message boundary and does not indicate the peer will stop sending.
10. **“After reading the header with a Reader, you can immediately use the raw InputStream for the body.”** Likely wrong because the reader has already read ahead. Design one consistent parser throughout.

## 14. Practical Checklist for Verifying a Byte-Splitting Bug

When a server receives JSON, Vietnamese text, or emojis turned into `�`, check in order:

1. **Capture bytes at both ends** (e.g., hex in a test environment, avoiding logging sensitive data). Compare the bytes produced by the sender with the bytes reassembled by the receiver *before decoding*.
2. If the bytes match on both sides, the issue is usually in **the decoder, charset, or framing**. Check whether `new String` is called on every `read` and whether the exact byte count `n` is used.
3. Intentionally test multiple read boundaries: 1 byte per read; splits inside 2-byte (`C3 A9`), 3-byte (`E2 82 AC`), and 4-byte (`F0 9F 98 80`) sequences; reassembly must preserve the exact text.
4. Verify that the application computes the header from `payload.length`, bounds the payload before allocation, and uses `readFully` or a loop reading all N bytes.
5. Test **truncated frames**, **invalid continuation bytes**, **overlong encodings**, **lone surrogates in Java input**, EOF, and timeouts; observe that errors are clearly categorized.
6. Check `String` size with `length()` and code point count with `codePointCount` to distinguish UTF-16 bugs from network bugs.
7. Re-measure with small/large buffers and sockets reading across multiple turns; the **content** result must be invariant, while only read counts and timing may vary.

In automated tests, compare the **final data** and frame count, avoiding assertions like “each `read` returns exactly X bytes.” That tests the real behavior of the protocol.

## 15. Key Takeaways

- **TCP preserves byte stream order, not UTF-8 or message boundaries.**
- **UTF-8 uses 1–4 bytes per code point; Java `char` is 16-bit UTF-16.** Count bytes for length-prefixes; count code points if you want code points.
- **Do not decode each TCP chunk into a `String` independently** if a chunk can split mid-character. Use `InputStreamReader`/a stateful decoder, or assemble all bytes of a frame first and then decode.
- **EOF, timeout, and malformed input are three distinct scenarios.** Do not ignore incomplete data or silently replace invalid characters.
- **Always separate framing from decoding.** Only a parser that knows “a full message has arrived” has a sound basis for handing valid text data to application logic.

API references: [Java SE 17 `InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html), [`CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html), [`DataInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html), [`String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [RFC 3629 — UTF-8](https://www.rfc-editor.org/rfc/rfc3629).
