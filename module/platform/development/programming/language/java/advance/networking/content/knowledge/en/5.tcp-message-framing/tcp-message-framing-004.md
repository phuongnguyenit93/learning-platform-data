# Reading the Exact Number of Bytes Needed and Retaining Data for the Next Message

## Objectives

In TCP, a single `read` **does not correspond** to one application message. After this lesson, you will be able to:

- Explain why TCP delivers a **continuous byte stream** to the application, meaning a message can be split across multiple reads or multiple messages can arrive in a single read.
- Design a way to determine **message boundaries** (framing), especially for a protocol with a **4-byte length + payload**.
- Read the **exact number of bytes needed** using `DataInputStream.readFully` or an `InputStream.read` loop, check for EOF, and avoid consuming past the message boundary.
- Retain bytes that do not yet belong to a complete message using a cumulation buffer with `ByteBuffer.flip()`, `mark()`, `reset()`, and `compact()`.
- Distinguish between **insufficient bytes**, **one complete frame**, and **having part of the next frame**; avoid mistaking `available()`, `readAllBytes()`, or a single `read` for a message boundary.
- Write and test a Java 17+ example that includes both a sequential reader and a decoder handling split/coalesced chunks.

**Scope:** applications using TCP with a protocol agreed upon by both endpoints. The examples encode text payloads in UTF-8, but **the length in the header is the number of bytes**, not the number of Java characters.

## 1. TCP Does Not Preserve Message Boundaries for the Application

TCP guarantees that the byte stream is delivered in order over a connection when no errors occur; TCP **does not** record how many times the sender called `write` so that the receiver can reconstruct individual application "messages".

Suppose the sender sequentially calls:

~~~java
output.write(frameA);
output.write(frameB);
~~~

The receiver may observe:

~~~text
Sender:   [frame A][frame B]       (two write calls)
Receiver: [A part 1] [A part 2 + B]      or
          [A + B]                         or
          [A][B part 1][B part 2]         ...
~~~

How chunks are divided depends on buffers, TCP segmentation, scheduling, and read timing. There is no guarantee that "each `write` produces exactly one `read`", even if they happen to match in localhost tests.

Three situations must be distinguished:

| Situation | Bytes obtained in one read | Conclusion |
|---|---|---|
| **Fragmented** | Only part of the current frame | Do **not** process yet; keep state, keep reading. |
| **Exact** | Just enough to complete the current frame | Process the frame, prepare to read the next frame. |
| **Coalesced / excess** | All of the current frame plus part or all of the next frame | Process the complete frame, **retain** the excess bytes for further parsing; do not discard them. |

All three are valid behaviors. The received bytes must be interpreted using the **framing rules of the application protocol**.

## 2. Framing Contract: 4-Byte Length and Payload

A common approach is *length-prefix framing*. In this lesson, we use the following specific convention:

~~~text
Frame = [4-byte unsigned-like length in network byte order][payload bytes]

Header: 4 bytes big-endian, read with Java DataInputStream.readInt()
Length: number of payload bytes; limited to 0..1024 in the sample protocol
Payload: UTF-8 bytes; may be an empty message if length=0
~~~

`readInt()` reads a **signed** 32-bit big-endian integer. Even if the sender treats the header as a non-negative length, negative numbers and numbers larger than the agreed limit must be rejected **before allocating an array**.

Example of two consecutive messages:

~~~text
Frame 1 "HELLO": 00 00 00 05  48 45 4C 4C 4F
Frame 2 "BYE":   00 00 00 03  42 59 45

TCP stream: 00 00 00 05 48 45 4C 4C 4F 00 00 00 03 42 59 45
            |--header--| |--HELLO--| |--header--| |--BYE--|
~~~

There are **16 bytes** on the stream: 9 bytes for the `HELLO` frame and 7 bytes for the `BYE` frame. A single `read` might return all 16 bytes, 1 byte, or another amount. To complete the first frame, the parser must consume only **4 + 5 = 9 bytes**. The remaining seven bytes must be used for the second frame.

**Unicode note:** the length on the wire must be calculated with `payload.getBytes(StandardCharsets.UTF_8).length`. For example, `"Việt".length()` is **4 UTF-16 code units**, but the UTF-8 encoding of that string is **6 bytes** (the character `ệ` takes 3 bytes). Using `String.length()` to send the header will cause the receiver to slice the payload incorrectly and desynchronize all subsequent frames.

### Invariants of a Correct Parser

At any moment, the parser has a **read position** within the received byte sequence:

1. If fewer than **4 header bytes** are available, do not attempt to read the length; retain the incomplete header bytes.
2. Once the header is available, verify that the length is within `0..MAX_FRAME`.
3. If fewer than `length` payload bytes are available, **do not process the incomplete message**; keep the necessary bytes intact and wait for more.
4. When enough bytes are available, consume **exactly** `4 + length` bytes of the completed frame and emit the message.
5. Any bytes **after** that position belong to the unparsed portion of one or more subsequent frames. Do not delete them, decode them prematurely, or read past and discard them.

~~~text
[already parsed][complete frame][incomplete header/payload of next frame]
                ^--- consume ---^
                                ^-- retain
~~~

From a single chunk, **0, 1, or more frames** may be completed. The parser must have a loop to process all complete frames, then retain the remainder.

## 3. The Simple Blocking Stream Approach: Request the Exact Number of Bytes

With `Socket.getInputStream()` in blocking mode, `InputStream.read(byte[])` only promises to read **at most** the requested number of bytes; returning fewer is normal. In many cases, the easiest correct approach is to use `DataInputStream`:

~~~java
static String readFrame(DataInputStream in) throws IOException {
    int length = in.readInt(); // Read all 4 header bytes, big-endian.

    if (length < 0 || length > 1024) {
        throw new IOException("Invalid frame length: " + length);
    }

    byte[] payload = new byte[length];
    in.readFully(payload);    // Returns only when all length bytes are read.
    return new String(payload, StandardCharsets.UTF_8);
}
~~~

**Method snippet**, placed in a class that imports `java.io.DataInputStream`, `java.io.IOException`, and `java.nio.charset.StandardCharsets`. A single `readFrame` call consumes **exactly** 4 header bytes and `length` payload bytes:
- `readInt()` waits for the full header or throws `EOFException` if EOF occurs before it is complete.
- `readFully(payload)` reads in a loop until all bytes are read, or throws `EOFException` if the stream ends early.
- If data for the next frame is already in the stream, it **has not been pulled out of the wrapper stream**. The next `readFrame` call continues reading at the exact remaining position.

When wrapping with `BufferedInputStream`, the internal buffer layer may **prefetch** data from the socket. That remains correct because the prefetched bytes are **held inside the live buffer itself**. You must keep **one stream wrapper instance for the entire connection**, rather than creating a new `BufferedInputStream` after each frame and discarding the old wrapper (doing so can lose prefetched bytes).

Usage example with an open socket (illustrative snippet, not a standalone program):

~~~java
socket.setSoTimeout(5_000); // Timeout for each blocking read operation.
DataInputStream input = new DataInputStream(
    new BufferedInputStream(socket.getInputStream())
);

String first = readFrame(input);
String second = readFrame(input); // Continues right where first stopped.
~~~

You need to import `java.net.Socket`, `java.io.BufferedInputStream`, and `java.io.DataInputStream`; the code above assumes `socket` is already initialized and `readFrame` is in the same class. Only **one reader thread** should own a connection's input stream so that two readers do not race for bytes. When closing the socket, close the stream and socket according to the connection's lifecycle; the example above does not show full resource lifecycle management.

**Advantages:** no need to manually manage an application buffer if you only read sequentially with blocking I/O and the API does not read past the required number of bytes. **Limitation:** if a framework or event loop hands you **an entire chunk containing excess bytes**, you must manage the excess bytes yourself as shown in the next section.

## 4. Why a `read` Loop Is Still Necessary

If you do not use `DataInputStream.readFully`, the equivalent is accumulating until **a fixed-length byte region** is filled:

~~~java
static void readExactly(InputStream input, byte[] target)
        throws IOException {
    int position = 0;
    while (position < target.length) {
        int n = input.read(
            target, position, target.length - position
        );

        if (n == -1) {
            throw new EOFException(
                "Truncated frame: read " + position
                + " of " + target.length + " bytes"
            );
        }
        if (n == 0) {
            // Should not happen with standard InputStream and len > 0;
            // prevents an infinite loop with unusual implementations.
            throw new IOException("InputStream made no progress");
        }
        position += n;
    }
}
~~~

This is a **method snippet** requiring imports `java.io.InputStream`, `java.io.IOException`, and `java.io.EOFException`. Loop invariant: `position` is the number of bytes already obtained; the next iteration requests only `target.length - position` bytes, so it never crosses the target boundary.

Comparison of Java 17+ APIs:

| API | Behavior |
|---|---|
| `InputStream.read(b, off, len)` | Returns at most `len` bytes, possibly fewer; `-1` on EOF. |
| `DataInputStream.readFully(b)` | Reads all `b.length` bytes or throws `EOFException`/`IOException`. |
| `InputStream.readNBytes(len)` | Attempts to read up to `len` bytes; if EOF occurs early, may return a shorter array. **Must check `result.length`**. |
| `InputStream.readAllBytes()` | Reads until **EOF**, unsuitable for long-lived TCP connections carrying multiple messages. |
| `InputStream.available()` | Estimates bytes readable **without blocking**; **not** the total frame length or message length. |

When working with a nonblocking `SocketChannel`, `read` can return **0** because no bytes are currently available. Those are different semantics: preserve the decoder state and wait for a readability signal (e.g., `Selector`), **do not busy-spin**. Do not mechanically apply blocking `DataInputStream.readFully` to nonblocking NIO.

## 5. The Read-Ahead Case: Retaining Data for the Next Frame

When a program receives byte chunks from an event loop or reads from a socket into a `byte[4096]`, a chunk may end in the middle of the next frame's header. You cannot discard the leftover bytes because they have already been removed from the stream; nor can you arbitrarily "put them back" into the socket.

Using the two frames above, splitting the stream into three chunks:

| Chunk | Bytes received in that call | Parser state after receiving |
|---|---|---|
| `1` (7 bytes) | `00 00 00 05 48 45 4C` | Has 5-byte payload header but only received `HEL`; no frame emitted yet. **Retain 7 bytes**. |
| `2` (4 bytes) | `4C 4F 00 00` | Completes `HELLO` so emit frame 1; `00 00` are the **first 2 header bytes of frame 2**, **retain 2 bytes**. |
| `3` (5 bytes) | `00 03 42 59 45` | Combines with the previous 2 bytes to form header `00 00 00 03` and `BYE`; emit frame 2; 0 bytes left. |

A chunk-receiving decoder must maintain **state across multiple calls**. At any point, it must know which bytes have been parsed and which remain incomplete. For example:
- `ByteBuffer` starts in **write mode**: `position` points to where new bytes will be written; `limit` is the capacity.
- After `put(...)`, call `flip()` to switch to **read mode**: `position = 0`, `limit` is the number of available bytes.
- When the header is complete, call `mark()` to record the start of the header, then read `length`. If the payload is not yet complete, call `reset()` to return to the **start of the header**, preserving the entire incomplete frame.
- After processing all complete frames, `compact()` moves **all remaining bytes** to the beginning of the buffer and switches back to write mode to receive the next chunk.

**Important:** `compact()` preserves the bytes from `position` to `limit`; it does not clear the buffer. Even if only 1 byte of a header remains, it is preserved for the next `offer` call.

## 6. Runnable Example: Reading Enough Bytes and Retaining Excess Bytes

The file **`TcpFramingDemo.java`** below demonstrates both paths:
- `readFrame` using `readInt` + `readFully` on a stream capped at 2 bytes per `read(byte[])`.
- `FrameDecoder.offer` accepting arbitrary chunks, emitting complete frames, and using `compact()` to retain the next frame's partial data.

The example runs **in memory** without opening a socket, so stdout is deterministic. In a real network application, input bytes come from a socket or I/O callback instead of `ByteArrayInputStream`.

~~~java
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class TcpFramingDemo {
    private static final int MAX_FRAME = 1024;

    static byte[] wire(String... messages) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        for (String message : messages) {
            byte[] payload = message.getBytes(StandardCharsets.UTF_8);
            out.writeInt(payload.length);
            out.write(payload);
        }
        return bytes.toByteArray();
    }

    static String readFrame(DataInputStream in) throws IOException {
        int length = in.readInt();
        if (length < 0 || length > MAX_FRAME) {
            throw new IOException("Invalid frame length: " + length);
        }
        byte[] payload = new byte[length];
        in.readFully(payload);
        return new String(payload, StandardCharsets.UTF_8);
    }

    static final class FrameDecoder {
        private ByteBuffer pending = ByteBuffer.allocate(8);

        List<String> offer(byte[] chunk, int from, int to)
                throws IOException {
            int count = to - from;
            if (from < 0 || count < 0 || to > chunk.length) {
                throw new IndexOutOfBoundsException();
            }

            ensureSpace(count);
            pending.put(chunk, from, count);
            pending.flip();

            List<String> messages = new ArrayList<>();
            while (pending.remaining() >= Integer.BYTES) {
                pending.mark(); // Start of the next frame's header.
                int length = pending.getInt();
                if (length < 0 || length > MAX_FRAME) {
                    throw new IOException(
                        "Invalid frame length: " + length);
                }
                if (pending.remaining() < length) {
                    pending.reset(); // Payload not yet complete.
                    break;
                }

                byte[] payload = new byte[length];
                pending.get(payload);
                messages.add(new String(
                    payload, StandardCharsets.UTF_8));
            }
            pending.compact(); // Retain bytes of the next frame.
            return messages;
        }

        int retainedBytes() {
            return pending.position(); // In write mode.
        }

        private void ensureSpace(int additional) {
            if (pending.remaining() >= additional) {
                return;
            }
            int required = pending.position() + additional;
            ByteBuffer larger = ByteBuffer.allocate(
                Math.max(required, pending.capacity() * 2));
            pending.flip();
            larger.put(pending);
            pending = larger;
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = wire("HELLO", "BYE");

        InputStream fragmented = new FilterInputStream(
                new ByteArrayInputStream(bytes)) {
            @Override
            public int read(byte[] b, int off, int len)
                    throws IOException {
                return super.read(b, off, Math.min(len, 2));
            }
        };
        DataInputStream in = new DataInputStream(fragmented);
        System.out.println("readFully 1: " + readFrame(in));
        System.out.println("readFully 2: " + readFrame(in));

        FrameDecoder decoder = new FrameDecoder();
        System.out.println("chunk 1: "
            + decoder.offer(bytes, 0, 7)
            + " | retained=" + decoder.retainedBytes());
        System.out.println("chunk 2: "
            + decoder.offer(bytes, 7, 11)
            + " | retained=" + decoder.retainedBytes());
        System.out.println("chunk 3: "
            + decoder.offer(bytes, 11, bytes.length)
            + " | retained=" + decoder.retainedBytes());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 TcpFramingDemo.java
java TcpFramingDemo
~~~

Exact stdout:

~~~text
readFully 1: HELLO
readFully 2: BYE
chunk 1: [] | retained=7
chunk 2: [HELLO] | retained=2
chunk 3: [BYE] | retained=0
~~~

### Code Explanation

1. `wire("HELLO", "BYE")` uses `DataOutputStream.writeInt` to send a 4-byte big-endian length, then `write` for the UTF-8 payload; the sender and receiver protocols match exactly.
2. `fragmented` forces `read(byte[], off, len)` to return at most 2 bytes at a time, yet `DataInputStream.readFully` still receives both `HELLO` and `BYE` in order. This tests **short reads**, not simulated network latency.
3. `FrameDecoder.offer(bytes, 0, 7)` receives the first 7 bytes, which is not enough for the 5-byte payload; `pending.reset()` moves the cursor back to the start of the header and `compact()` retains 7 bytes.
4. The second call adds 4 bytes: the parser has all 9 bytes of the `HELLO` frame, leaving the first 2 header bytes of `BYE` in `pending`. `compact()` retains exactly **those 2 bytes**.
5. The third call adds 5 bytes, completing the 4-byte header and 3-byte `BYE` payload. The parser emits `BYE`, with 0 bytes remaining.
6. The `while` loop can emit **multiple** frames in a single `offer` call if the chunk contains multiple complete frames; any incomplete trailing data is retained. No branch loses bytes of a subsequent frame.

This example demonstrates growing the buffer according to chunk size and does not implement a total memory limit for abnormal input. In a real system, you must **limit chunk size, pending byte count, frame length, and rate/timeout**, or use a streaming state machine with a fixed buffer. `MAX_FRAME` prevents oversized payloads, but **does not by itself prevent** an `offer` call from passing a huge chunk; do not treat the demo code as an Internet-ready decoder without adding limits.

## 7. Three Subtle Bugs to Watch Out For

### Bug A: Treating `read` as One Message

~~~java
byte[] buf = new byte[4096];
int n = input.read(buf);
String message = new String(buf, 0, n, StandardCharsets.UTF_8);
~~~

The snippet above only builds text from the **chunk just received**; it does not prove the chunk is a frame. If a multi-byte UTF-8 sequence is split across a read boundary, decoding per chunk can also corrupt characters (producing replacement characters). Only decode a **complete payload** after framing.

### Bug B: Reading More Than Needed and Discarding the Remainder

~~~java
int n = input.read(buf);
processOnlyFirstFrame(buf, n);
// Forgot to save buf from the end of the first frame to n.
~~~

If `n` includes initial bytes of the next frame, the parser has already **consumed** them from the socket but discarded them from memory. The next read starts mid-frame, the header will be wrong, and the entire stream loses synchronization. You must retain the `[endOfFirstFrame, n)` slice or use a decoder with a cursor/`compact`.

### Bug C: Assuming EOF, Timeout, and Short Read Are the Same

- `n > 0` but fewer than expected: **valid short read**, keep accumulating.
- `n == -1`: **EOF** — the peer closed its send side; if in the middle of a header/payload, it is a **truncated frame**.
- `SocketTimeoutException`: the blocking read waited longer than `SO_TIMEOUT`; it **does not** mean the frame ended. Depending on policy, continue with the retained state or close the connection; do not treat missing bytes as a complete message.
- Nonblocking `SocketChannel.read` returning `0`: no bytes available yet; wait for readiness, do not treat as EOF.

`readInt()` when EOF occurs before or during the header normally throws `EOFException`; if you need to distinguish a **clean close on a frame boundary** from a **truncated header**, write a header read that detects `-1` before the first byte. Do not assume `EOFException` always means a valid message was completed.

## 8. Limits, Performance, and Connection Lifecycle

**Validate length before allocating.** Headers from the network are untrusted data. Set `MAX_FRAME` according to the protocol and quota; reject negative lengths, lengths exceeding the limit, or invalid formats. When converting `long` to `int` or computing `header + payload`, check for overflow. For large payloads, consider streaming in chunks into a bounded sink rather than allocating huge arrays.

**Timeouts and slow senders.** `socket.setSoTimeout(5_000)` applies to each blocking read operation on the socket; it **does not mean** a 5-second deadline for the entire frame. A sender can trickle data and stretch out total duration. Production systems need an overall deadline, inter-byte idle limits, quotas, and a disconnect policy.

**Only one parser owns the byte stream.** Multiple threads reading the same `InputStream` can steal each other's headers/payloads. A reliable pattern is having a single reader/decoder responsible for framing, which then dispatches **complete messages** to business-logic workers.

**Keep both endpoints' protocols aligned.** Both sides must agree on header width/endianness, whether the length includes the header, payload charset, size limits, and frame ordering. `DataInputStream.readUTF()`/`DataOutputStream.writeUTF()` use **modified UTF-8** with their own length mechanism; they are **not** automatically compatible with the 4-byte length + standard UTF-8 protocol in this lesson.

**Buffer across frames.** If wrapping input with `BufferedInputStream`, keep the wrapper for the stream's entire lifetime; if using `FrameDecoder`, keep the same instance across chunks. Never clear `pending` while frames remain unparsed, and never try to re-read from the socket bytes that a callback has already handed to the application.

**Errors belong to connection state.** If you encounter a malformed header or truncated payload, consider closing the connection and recreating the parser from scratch on a new connection; trying to "guess where the next frame starts" in a byte stream without synchronization markers is usually unreliable.

## 9. Other Framing Styles and Their Trade-offs

| Framing style | Principle | Key considerations |
|---|---|---|
| **Fixed-size** | Every message is exactly N bytes | Only suitable when size is always constant; must read all N bytes. |
| **Length-prefix** | Header declares payload length | Validate length; read exact bytes; retain data after the frame. |
| **Delimiter-based** | Special character/byte separates messages, such as LF | Payload needs delimiter escaping or encoding rules; delimiter may span chunks. |
| **EOF-delimited** | EOF marks the end | Only suitable when one direction closes after the content; unsuitable for multiple messages on a long-lived connection without added structure. |

With delimiter-based framing, you cannot simply search for `'\n'` within **each individual chunk** and discard what comes before/after: incomplete bytes must be retained across reads. With length-prefix framing, boundaries are determined by byte count, so payloads can freely contain bytes that look like delimiters without ambiguity.

## 10. Decoder Testing Checklist

When testing a real protocol, create reproducible inputs:

1. **Fragmented header:** 4 length bytes arrive as `1 + 1 + 2`; the decoder must not read the length early or emit bogus messages.
2. **Fragmented payload:** header is complete, but payload arrives across multiple chunks; emit only after the final byte.
3. **Two frames in one chunk:** emit both in order.
4. **One frame plus an incomplete next header:** emit the first frame, retain the exact bytes of the next header.
5. **Empty frame:** length 0 is valid if the protocol allows it.
6. **Truncated EOF:** missing a header/payload byte reports an appropriate error; never emit a partial message.
7. **Negative length or exceeding `MAX_FRAME`:** reject before allocating or growing buffers past quota.
8. **Multi-byte UTF-8 payload:** header length is `byte[].length`; never partially decode in the middle of a character.
9. **Randomly sized chunks:** split the same wire sequence into various partitions, then compare the emitted frame list and retained byte state against expected results.
10. **Resource limits:** slow senders, huge declared lengths, garbage data, or many concurrent connections must not cause unbounded memory allocation.

What you should assert is the **list of emitted frames and the unread bytes**, not the number of `read` calls the OS chose to return.

## 11. Practice Exercises

1. Why do two `socket.getOutputStream().write(...)` calls on the sender not guarantee that the receiver will have exactly two `read(...)` calls?
2. Given the stream `00 00 00 05 HELLO 00 00 00 03 BYE`, if the parser receives the first 11 bytes, what must it emit and how many bytes must it retain?
3. Modify `FrameDecoder` so that when `offer` receives a chunk containing **both** frames, the return value has two messages and `retainedBytes() == 0`. Does the `while` loop need to be changed?
4. Try the payload `"Việt"`. Why would using `"Việt".length()` as the header value be wrong? Verify the UTF-8 byte length.
5. Design a test for the case where only 3 of 4 header bytes are received before the sender closes the connection.
6. State what can happen if a new `new BufferedInputStream(socket.getInputStream())` is created for every frame read and the old wrapper is discarded.
7. If `InputStream.readNBytes(100)` returns only 73 bytes due to EOF, what condition determines whether that is a valid frame or a truncated one?
8. Why should you not use `input.available() == expectedLength` to determine whether a full frame has arrived?

**Key answers:** (1) TCP only preserves byte order; (2) emit `HELLO`, retain the **first 2 header bytes of the `BYE` frame**; (3) no change needed if the `while` loop already parses until bytes are insufficient, in which case it returns both; (4) UTF-8 requires **6 bytes**, unlike 4 UTF-16 code units; (5) detect a truncated header and emit no frame; (6) prefetched bytes are lost; (7) valid only if the framing actually required 73 bytes, whereas if 100 were expected it is truncated; (8) `available` does not reflect total message bytes or bytes that will arrive later.

## 12. Key Takeaways

- **TCP is a byte stream with no message boundaries.** Framing belongs to the application protocol.
- **Read completely:** use `readFully` or a loop that accumulates the exact `remaining` bytes, handling EOF and timeouts separately.
- **Do not over-read and discard.** If a read chunk includes bytes from the next frame, retain the unparsed portion with a cursor/buffer; `compact()` is one way to do this.
- **Parse by bytes.** The length header of a UTF-8 payload must be measured in **bytes**; decode to `String` only after the full payload has arrived.
- **One parser per stream**, with length/buffer limits, timeouts, and tests covering all chunk splitting and coalescing patterns.

### References

- [Oracle Java SE 21 — InputStream: read, readNBytes, available](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html)
- [Oracle Java SE 21 — DataInputStream and readFully](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataInputStream.html)
- [Oracle Java SE 21 — ByteBuffer: flip, compact, mark, reset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html)
- [Oracle Java SE 21 — Socket: setSoTimeout, getInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html)
- [RFC 9293 — Transmission Control Protocol (TCP)](https://www.rfc-editor.org/rfc/rfc9293.html)
