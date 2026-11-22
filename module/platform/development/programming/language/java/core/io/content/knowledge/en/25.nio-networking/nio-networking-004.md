# TCP Is a Byte Stream and Does Not Preserve Message Boundaries — Java NIO Networking

## 1. Lesson Objectives

When two applications exchange data over TCP, the sender may call `write()` multiple times, yet the receiver **has no guarantee that each `read()` corresponds to one `write()`**. TCP provides **an ordered byte stream**, not a built-in notion of an application-level "message".

This is a foundational point when programming `SocketChannel`, `ServerSocketChannel`, and `ByteBuffer` in Java NIO. If ignored, applications easily run into bugs: truncated JSON, two commands glued together, broken UTF-8 decoding, or protocols hanging because neither side knows whether a message has ended.

After this lesson, you will be able to:

- Explain accurately why one TCP write does not equal one TCP read.
- Distinguish between **TCP segment**, **byte stream**, **application message**, and **frame**.
- Design protocols that define message boundaries using length prefixes, delimiters, or fixed sizes.
- Read/write complete byte counts with `SocketChannel`, handling return values smaller than expected, `0`, and `-1`.
- Use `ByteBuffer` properly, especially `flip()`, `clear()`, and `compact()`.
- Prevent bugs related to frame size, UTF-8, blocking/non-blocking behavior, and partial data arrivals.

## 2. What Does TCP Provide and What Does It Not?

TCP is a **connection-oriented** protocol that delivers an ordered sequence of bytes. While the connection is active and data is successfully received, TCP reassembles data in stream byte order; sequence numbers, retransmission, flow control, and congestion control operate beneath the application.

However, **TCP does not define application message boundaries**. For example, suppose the sender executes:

~~~text
write("ABC")
write("DEF")
write("GHI")
~~~

The receiver may observe read results such as:

~~~text
Read 1: "ABCDEFGHI"
~~~

or:

~~~text
Read 1: "A"
Read 2: "BCDE"
Read 3: "FGHI"
~~~

or other splits, as long as byte order is preserved. These are **illustrative possibilities**, not fixed rules of TCP or any particular JVM.

The same holds when the sender packs all bytes into **a single** `write()`: a single `read()` may return fewer bytes. Conversely, if sent with multiple `write()` calls, a single `read()` may return bytes from multiple write calls.

### Distinguishing the Layers

| Concept | Defined by | Is it an application message boundary? |
| --- | --- | --- |
| TCP segment | TCP stack / network path | **No** |
| `SocketChannel.write(...)` calls | Sender code | **No** |
| `SocketChannel.read(...)` calls | Receiver code, available data, and channel state | **No** |
| Application protocol frame | Your protocol design (or HTTP, WebSocket, etc.) | **Yes**, if defined properly by the protocol |
| Business message | Application | May reside inside one frame or be assembled from multiple frames per protocol |

Do not deduce that "each TCP packet is a message". Typical Java applications receive **bytes on a socket**, not a direct list of TCP segments to reassemble per packet.

> **Rule:** The receiver must determine where a message ends on its own. Apply **message framing** instead of guessing from `read()` counts.

## 3. Why Can Data Be Split or Coalesced?

Suppose a client sends two commands:

~~~text
LOGIN alice
PING
~~~

Without a command terminator or a length field, the receiver only sees the byte sequence `LOGIN alicePING` and **has no general way to know where to split**.

Even if the client calls `write()` twice separately, TCP and the OS can split or coalesce data due to several factors:

1. **Application buffer size:** if the receive buffer only has 4 bytes of space left, `read()` cannot place 10 bytes into it.
2. **Read timing:** data from multiple writes may already have arrived before a single read call.
3. **TCP segmentation/retransmission:** how bytes traverse the network is not a message interface for the application.
4. **Non-blocking sockets:** the current read may receive only a partial chunk, or no bytes yet.
5. **Backpressure:** a slow receiver/destination causes the number of bytes accepted in one write to be smaller than requested.

Common terms for this are "sticky packets" or "packet fragmentation" at the application layer; a more accurate framing is **an application that has not yet designed or handled framing over a byte stream**.

TCP does not lose **boundaries** it once promised to keep: from the start, TCP **never promised to preserve message boundaries**.

## 4. Reading and Writing with `SocketChannel`: Always Check Actual Byte Counts

In Java NIO:

~~~java
int readBytes = socketChannel.read(readBuffer);
int writtenBytes = socketChannel.write(writeBuffer);
~~~

Both calls return the **actual** number of bytes read/written in that call, not necessarily equal to the prior `ByteBuffer.remaining()`.

### For `read(ByteBuffer)`

- **Positive** value: that many bytes were read, and the buffer's `position` advances by that exact count.
- **0**: no bytes were read this time. For a **non-blocking** channel, this usually means no data is immediately readable; it can also happen if the buffer has no remaining space.
- **-1**: **end-of-stream (EOF)** was reached, meaning the peer has ended its sending direction and any remaining queued bytes have been consumed.
- Throws `IOException`: I/O failure, closed channel, connection reset, or other conditions; do not equate all errors with normal EOF.

In **blocking** mode, if the buffer has room, a read typically waits until at least one byte, EOF, or an error occurs; **it does not wait for an entire application message**. A successful read call can return as little as 1 byte.

### For `write(ByteBuffer)`

- **Positive** value: part or all of the buffer's remaining bytes were accepted by the channel; the buffer's `position` advances accordingly.
- **0**: the call wrote no bytes, which can happen especially in non-blocking mode. Do not infer that the peer has finished receiving data.
- A successful `write()` return **does not guarantee the peer has read/processed** those bytes at the application layer.

Basic loop example in blocking mode:

~~~java
while (buffer.hasRemaining()) {
    int n = channel.write(buffer);
    if (n == 0) {
        throw new IOException("Socket ghi không tiến triển");
    }
}
~~~

This snippet is illustrative only; it requires `channel` to be a **blocking** `SocketChannel`, `buffer` already flipped via `flip()` to be ready for reading out, and `import java.io.IOException`. In non-blocking mode, if `write()` returns 0, **register interest in writability** with `Selector` or an equivalent event mechanism rather than spinning on the CPU.

## 5. Three Ways to Design Message Boundaries

### 5.1. Length-prefix framing: placing the length up front

Each frame starts with the payload length, followed by that exact number of payload bytes. For example, using a 32-bit (4-byte) **big-endian** integer—unsigned in protocol semantics, though when read as a Java `int` its valid range must be validated:

~~~text
[ 00 00 00 05 ][ H E L L O ][ 00 00 00 04 ][ J A V A ]
      4 bytes       5 bytes         4 bytes      4 bytes
      length=5                      length=4
~~~

The receiver follows these steps:

1. Read **all 4 bytes** of the header, even across multiple `read()` calls.
2. Decode the length using the agreed endianness; reject negative values, overly large values, or values exceeding protocol limits.
3. Read **the exact declared number of payload bytes**.
4. Only when all bytes have arrived should you decode the payload and process a message.
5. Repeat step 1 for the next frame, even if bytes of the next frame are already sitting in the receive buffer.

**Pros:** payloads can contain arbitrary bytes, including newlines or `0` bytes; completeness is easy to verify. **Cons:** requires tracking header/payload state when data arrives incrementally, and validating length before allocating memory.

A production protocol should specify header width, endianness, maximum size, payload encoding, versioning, malformed frame handling, and timeout policies.

### 5.2. Delimiter framing: separator markers

For example, text commands terminated by LF (`\n`):

~~~text
PING\n
LOGIN alice\n
~~~

The receiver accumulates bytes until the LF marker and splits the message. This is a simple choice for line-oriented protocols.

**Cautions:**

- The delimiter may appear inside payloads; you must define escaping/quoting or forbid it in content.
- When using UTF-8, ensure correct decoding even when a multi-byte character is split across reads; typically split/reassemble **bytes** first and then decode the whole message, or use a stateful `CharsetDecoder`.
- Enforce a maximum line length. If a peer sends endlessly without `\n`, the server must not grow buffers without bound.
- Clearly specify `\n` vs `\r\n`, as well as how a final line ending at EOF is handled.

### 5.3. Fixed-size framing: every frame has a fixed size

If every record is always exactly 32 bytes, the receiver simply accumulates 32 bytes and processes it. This fits binary protocols with fixed schemas.

Drawbacks: variable-length data needs padding or a length field; shorter records cannot be inferred automatically. **You still must loop reading** until all 32 bytes arrive, because each `read()` may return fewer.

### Which approach should you choose?

| Protocol | Pros | Points to watch |
| --- | --- | --- |
| Length-prefix | Explicit size; supports arbitrary binary payloads | Bounds checks, endianness, header/body state |
| Delimiter | Easy to read/debug with text | Escaping, line-length limits, encoding |
| Fixed-size | Simple for uniform records | Padding overhead, awkward for variable-length payloads |
| Terminated by EOF | Can work for **a single final payload** on a connection | Cannot separate multiple messages on a long-lived connection |

Avoid using **idle time**, `available()`, buffer size, or `read()` counts to guess whether a message is complete. None of those define protocol boundaries.

## 6. Complete Java 17+ Example: Two Messages in One TCP Stream

The following example creates a TCP server on loopback with an OS-assigned port, a client sends two consecutive frames, and the server reads exactly two messages using length-prefix framing.

To clearly show that one message may require **multiple reads**, `readExactly` intentionally caps each read to at most **3 bytes** via `ByteBuffer.slice()`. This is a limit **deliberately imposed by the example**, not network segmentation behavior guaranteed by TCP.

Save file **`TcpMessageFramingDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.FutureTask;

public class TcpMessageFramingDemo {
    private static final int MAX_FRAME_BYTES = 1024;
    private static final int READ_CHUNK = 3;

    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(
                    new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));

            FutureTask<List<String>> received = new FutureTask<>(() -> {
                try (SocketChannel peer = listener.accept()) {
                    return List.of(readFrame(peer), readFrame(peer));
                }
            });
            Thread serverThread = new Thread(received, "tcp-frame-reader");
            serverThread.start();

            try (SocketChannel client = SocketChannel.open()) {
                client.connect((InetSocketAddress) listener.getLocalAddress());

                byte[] first = "HELLO".getBytes(StandardCharsets.UTF_8);
                byte[] second = "JAVA".getBytes(StandardCharsets.UTF_8);

                // Two consecutive frames in ONE application ByteBuffer.
                ByteBuffer outgoing = ByteBuffer.allocate(
                        Integer.BYTES + first.length
                                + Integer.BYTES + second.length);
                outgoing.putInt(first.length).put(first);
                outgoing.putInt(second.length).put(second);
                outgoing.flip();

                // A single write call must not be assumed to flush the entire buffer.
                while (outgoing.hasRemaining()) {
                    int written = client.write(outgoing);
                    if (written == 0) {
                        throw new IOException("Blocking write không tiến triển");
                    }
                }
            }

            List<String> messages = received.get();
            System.out.println("Message 1: " + messages.get(0));
            System.out.println("Message 2: " + messages.get(1));
            System.out.println("Frame count: " + messages.size());
        }
    }

    private static String readFrame(SocketChannel channel)
            throws IOException {
        ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);
        readExactly(channel, header);
        header.flip();

        int byteLength = header.getInt();
        if (byteLength < 0 || byteLength > MAX_FRAME_BYTES) {
            throw new IOException("Invalid frame length: " + byteLength);
        }

        ByteBuffer payload = ByteBuffer.allocate(byteLength);
        readExactly(channel, payload);
        payload.flip();
        return StandardCharsets.UTF_8.decode(payload).toString();
    }

    private static void readExactly(SocketChannel channel, ByteBuffer dst)
            throws IOException {
        while (dst.hasRemaining()) {
            ByteBuffer step = dst.slice();
            step.limit(Math.min(step.remaining(), READ_CHUNK));

            int n = channel.read(step);
            if (n == -1) {
                throw new EOFException(
                        "EOF giữa frame, còn thiếu "
                                + dst.remaining() + " byte");
            }
            if (n == 0) {
                // Demo uses a blocking SocketChannel and the buffer still has space.
                // Non-blocking requires Selector or an equivalent waiting mechanism.
                throw new IOException("Blocking read không tiến triển");
            }

            // Since reading goes through slice, update the original buffer's position manually.
            dst.position(dst.position() + n);
        }
    }
}
~~~

Compile/run from the directory containing the file with **JDK 17+**:

~~~bash
javac -encoding UTF-8 TcpMessageFramingDemo.java
java TcpMessageFramingDemo
~~~

**Stdout** when loopback connections work normally:

~~~text
Message 1: HELLO
Message 2: JAVA
Frame count: 2
~~~

### Explanation of Key Points

1. `listener.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0))` listens only on loopback; port `0` asks the OS to pick an available port. The program queries the bound address directly, so stdout does not depend on port numbers.
2. Server and client use `SocketChannel` in **default blocking mode**. The server thread waits on `accept()` and reads two frames. The main thread sends both frames and waits for results via `FutureTask.get()`.
3. `outgoing.putInt(first.length)` writes a 4-byte header in the default **big-endian** byte order, followed by the payload. Likewise for the second frame. The two frames sit back-to-back inside 17 application data bytes.
4. `outgoing.flip()` switches the buffer from **writing bytes into the buffer** to **reading bytes out of the buffer to send over the socket**. The `while (outgoing.hasRemaining())` loop handles partial writes.
5. `readFrame` must collect all 4 bytes before calling `getInt()`, then collect exactly `byteLength` payload bytes. It never assumes that because the client sent two frames back-to-back, the server will receive both in one `read()`.
6. `readExactly` sets `step.limit(...)` to at most 3 bytes. Thus the 4-byte header and 5-byte payload necessarily require **multiple `read()` calls** even if the network already delivered all bytes. `step` is a `slice` sharing backing memory with `dst` while maintaining independent position/limit, so `dst.position()` must be updated after each read.
7. If the peer closes the connection before sending the full header or payload, `readExactly` gets `-1` and throws `EOFException`; the incomplete message is **not** processed as a complete message.
8. The `MAX_FRAME_BYTES` limit is checked **before allocating** the payload buffer; this prevents a forged header from requesting an arbitrarily large allocation.
9. `UTF_8.decode(...)` runs only after the full payload has arrived. The example uses ASCII data in UTF-8, so no character is split across reads.

**Takeaway from the example:** Two messages are sent back-to-back on **one TCP stream**, while splitting them into two messages on the receiver depends solely on the **length header**. Individual read sizes do not determine message count.

## 7. Data Accumulation Pattern with `ByteBuffer` in Non-blocking Applications

In non-blocking mode (`channel.configureBlocking(false)`), `read()` can return 0 because no data is currently available. You must not apply the blocking `readExactly` above verbatim to **sit and wait** for a frame; instead, preserve parse state across read events.

The processing loop typically follows this idea:

1. When `Selector` signals the channel is readable, call `channel.read(buffer)`; the result can be positive, 0, or -1.
2. Switch the buffer to read mode with `flip()`.
3. Extract **complete frames** currently accumulated. If fewer than 4 header bytes or incomplete payload bytes are present, retain the unprocessed portion.
4. Call `compact()` to shift unread bytes to the beginning of the buffer, making space to receive more data. When all bytes have been consumed, `clear()` is also appropriate.
5. Wait for the next read event. If `read() == -1` while a partial frame remains, report an early-termination protocol error.

Example ByteBuffer lifecycle:

~~~text
New/clear:         position=0, limit=capacity   (ready to write data in)
Socket read:       channel.read(buffer)         (position advances by bytes received)
flip:              limit=position, position=0   (ready to parse)
Partial parse:     position advances by bytes consumed
compact:           keeps unparsed bytes         (ready for next socket read)
~~~

**Do not confuse `clear()` with erasing memory:** `clear()` only resets position and limit indices; if unprocessed bytes remain, calling `clear()` can let them be overwritten. `compact()` is the right choice when unparsed data must be preserved.

### One Read Can Yield 0, 1, or Many Frames

A proper parser must handle all three situations:

- **0 complete frames:** only a partial header or partial payload arrived; wait for more bytes.
- **1 complete frame:** emit one message and keep any remainder.
- **Multiple complete frames:** continue parsing inside the current buffer until insufficient data remains for the next frame.

For example, the buffer may currently hold:

~~~text
[length=3][CAT][length=3][DOG][length=5][HE...
~~~

The parser emits `CAT` and `DOG`, while **retaining the third frame's header and the two bytes `HE`**. Only when the next read supplies `LLO` can the message `HELLO` be processed.

When a frame can exceed the socket read buffer size, the parser must hold independent state: read header, validate length, allocate/collect bounded payload, and then process. Never assume a single fixed socket buffer can hold every frame.

### Non-blocking Writes Also Have Partial State

If `channel.write(outgoing)` writes only 7 out of 20 bytes, **keep the buffer with its remaining 13 bytes**. When writability is ready, continue from the current `position`. If it returns 0, register interest in `SelectionKey.OP_WRITE` while pending data remains, and disable write interest once the queue is empty to avoid unnecessary write-event wakeups.

You must define a **backpressure** policy: cap outbound queues, pause reading more input, or reject requests when a peer reads too slowly. TCP does not automatically bound memory for application message queues.

## 8. UTF-8 and Message Boundaries Are Not Character Boundaries

A UTF-8 character can take 1–4 bytes. Suppose the character `Đ` is encoded into multiple bytes; if one `read()` gets the first byte and the next gets the remaining byte(s), decoding each chunk independently can produce malformed or replacement characters.

**Safe procedure for length-prefix protocols:**

1. Measure payload length in **UTF-8 bytes** (`text.getBytes(StandardCharsets.UTF_8).length`), not `String.length()`.
2. Send the header as the **byte** count, then send the exact payload bytes.
3. On the receiver, gather all bytes before decoding the entire payload, or use a stateful `CharsetDecoder` across chunks.
4. Process the message only after the content is valid per schema.

For example, the string `"Xin chào"` has **more** UTF-8 bytes than the character count a reader sees. If the header used `text.length()` instead of `encoded.length`, the receiver would cut mid-payload and corrupt framing for subsequent messages as well.

`ByteBuffer.order(ByteOrder.BIG_ENDIAN)` or the big-endian default governs how header integers are read. Header endianness is **distinct** from body UTF-8 encoding; both must be clearly specified.

When data arrives from untrusted parties, `StandardCharsets.UTF_8.decode` replaces malformed UTF-8 byte sequences under its default policy. If invalid data must be rejected, use a `CharsetDecoder` with `CodingErrorAction.REPORT` and catch decoding errors rather than silently accepting corrupted messages.

## 9. EOF, Half-Close, Connection Closing, and Timeouts

### What does `read() == -1` mean?

`-1` indicates that **input from the peer has ended** and no more bytes remain to receive in that direction. For a length-prefix protocol:

- If a complete frame was read and `-1` arrives cleanly at the start of a new frame, that can be considered a valid end-of-stream **if the protocol allows closing at frame boundaries**.
- If only 2/4 header bytes or 7/10 payload bytes arrived, `-1` is a **truncated frame** and must be reported as an error.
- If the protocol requires mandatory frames or a specific frame count, closing even at a frame boundary may still be a business/protocol error.

TCP also supports **half-close**: the sender can end its sending direction with `SocketChannel.shutdownOutput()` while still reading responses in the reverse direction. Thus, EOF in the receive direction does not necessarily mean both directions closed simultaneously.

### Do not use silence intervals to conclude a message ended

If the server receives no more bytes for 50 ms, that **does not prove** the frame is finished. Network latency, scheduling, congestion, or peer load can all delay subsequent arrivals.

A **timeout** is an operational tool for handling slow/stalled connections; it is **not a message delimiter**. If a timeout expires mid-frame, decide whether to abort the frame/connection or retry according to the specific protocol.

### A successful `write()` is not processing confirmation

Java reporting that N bytes were written generally only means the channel accepted N bytes on the sending side. To know the peer has **successfully processed the business operation**, the protocol must include an ACK/response carrying a request identifier. Nor does TCP automatically guarantee "exactly once" message delivery across disconnects and reconnects; if clients retry, the server needs idempotency/deduplication logic when required by business rules.

## 10. Security and Robustness Checks for Frames

An improperly implemented framing protocol easily becomes a server vulnerability:

| Risk | Example | Mitigation |
| --- | --- | --- |
| Forged length header | Peer sends length `2_000_000_000` | Enforce `MAX_FRAME_BYTES` before allocating |
| Negative length header | `getInt()` returns `-1` | Reject negative values and out-of-bounds lengths |
| Sending partial frame and holding connection | Only 1/4 header bytes sent | Timeouts, connection quotas, receive deadlines |
| Unbounded delimiter line | Peer never sends `\n` | Cap maximum message length and drop offending connections |
| Premature decoding | Chunk contains half of a UTF-8 character | Accumulate full bytes or use a stateful decoder |
| Unbounded accumulation | Frames arrive faster than processing rate | Backpressure, bounded queues, pending frame limits |
| Multiple requests on one connection | Back-to-back payloads | Loop parser over multiple frames and retain remainder |
| Peer disconnects mid-frame | `read() == -1` while payload incomplete | Detect truncated frames; never process partial data |
| Client writes continuously without reading | `write()` keeps returning 0 in non-blocking | Wait for `OP_WRITE`, manage timeouts and queues |
| Assuming written means peer finished | Connection drops after `write` | Application-level confirmation, request IDs/idempotency where needed |

### Check size before creating objects

If the header is an `int`, validate immediately:

~~~java
int length = header.getInt();
if (length < 0 || length > MAX_FRAME_BYTES) {
    throw new IOException("Invalid length: " + length);
}
ByteBuffer payload = ByteBuffer.allocate(length);
~~~

This is an **illustrative snippet** requiring `header` to already have 4 bytes in read mode, `MAX_FRAME_BYTES` as a valid configured limit, and imports for `ByteBuffer` and `IOException`. Along a multi-frame read path, also bound **total** memory and connection counts, not just individual frames.

## 11. Common Mistakes in Java NIO Network Programming

**Mistake 1 — Treating one read as one message.**

~~~java
int n = channel.read(buffer);
// Wrong: immediately treating the n bytes as a complete message.
~~~

`n` is the number of bytes received in that read call, not the message length. Parse according to your framing protocol.

**Mistake 2 — Assuming one write sends everything.**

~~~java
channel.write(buffer);
// Wrong: ignoring buffer.hasRemaining() and unsent bytes.
~~~

Retain the buffer and continue writing; in non-blocking mode, wait until writable.

**Mistake 3 — Discarding partial headers/payloads.** Reading 2 bytes of a 4-byte header and discarding them causes the next 2 bytes to be misinterpreted as the start of a corrupted header.

**Mistake 4 — Parsing only one frame when the buffer holds several.** Causes unnecessary latency or loses leftover bytes if the buffer is cleared with `clear()` before processing the remainder.

**Mistake 5 — Using `read() == 0` as EOF.** `0` means no bytes in that read; `-1` is EOF. In non-blocking mode, handle `0` by waiting for the appropriate readiness event.

**Mistake 6 — Using `String.length()` as the UTF-8 byte count.** Easily splits multi-byte characters and desynchronizes the entire subsequent frame stream.

**Mistake 7 — Omitting frame size limits.** A peer can send a header requesting huge allocations, causing overload or out-of-memory failures.

**Mistake 8 — Calling `clear()` while unparsed bytes remain.** The buffer loses track of the remainder; `compact()` is appropriate when leftover data must be preserved.

**Mistake 9 — Relying on TCP_NODELAY or packet sizes to create boundaries.** `TCP_NODELAY` affects certain coalescing/latency behaviors, **it does not turn TCP into a message-oriented transport**. Framing is still mandatory.

**Mistake 10 — Assuming EOF is always a valid frame end.** If a header promised 100 bytes and only 60 arrived, that is a truncated message and must raise an error.

## 12. Self-Check Questions

**Question 1.** A client calls `write("HELLO")` then `write("JAVA")`. Can a single server `read()` call receive `"HELLOJAVA"`?

**Answer:** Yes. TCP is a byte stream; two writes can appear combined in a single read.

**Question 2.** A `read()` returns 3 bytes of a 4-byte header. What should the receiver do?

**Answer:** Keep the 3 received bytes, read 1 more byte to complete the header, and only then decode the length. Do not treat those 3 bytes as a message.

**Question 3.** A header specifies a 30-byte payload, yet the first read returns only 8 bytes. Is the data corrupted?

**Answer:** Not yet. This is a normal partial read; continue accumulating the remaining 22 bytes. Only if the peer closes before all bytes arrive should you conclude the frame was truncated.

**Question 4.** `read()` returns 0 on a non-blocking `SocketChannel`. Should the connection be closed as EOF?

**Answer:** No. `0` only means that call read no bytes; typically you wait for `Selector` to report read readiness.

**Question 5.** `write()` on a 1,024-byte buffer returns 600. How many bytes remain to send next?

**Answer:** 424 bytes remain unwritten. `ByteBuffer.position()` already advanced by the amount written, so continue calling `write` with **that same buffer** when the channel allows.

**Question 6.** Can you send UTF-8 `"Xin chào"` with a header set to `String.length()`?

**Answer:** Not if the header counts payload bytes; you must encode to UTF-8 first and use `encoded.length`.

**Question 7.** After receiving 2 full frames while the first 2 bytes of a third frame's header remain in the buffer, can you call `clear()`?

**Answer:** You should not, as it would discard the partial header data. Preserve the remainder using `compact()` or an equivalent buffer mechanism.

**Question 8.** If an application needs to distinguish commands over a single long-lived TCP connection, can it use EOF as a separator?

**Answer:** No. EOF only signals the end of the sending direction; use length-prefix, disciplined delimiters, or fixed-size framing to separate multiple commands.

## 13. Key Takeaways

- **TCP = ordered byte stream**, **no TCP-preserved message boundaries**.
- **`write()` does not map 1:1 to `read()`**. One message may span multiple reads; one read may hold multiple messages.
- **Framing is the application protocol's responsibility**: length-prefix, delimiter, or fixed-size; never guess from packets, buffers, or timing.
- Java NIO reads/writes must inspect **actual byte counts**; `read() == -1` is EOF, `0` is not EOF; non-blocking code must keep state and wait for readiness.
- Use `flip()`/`compact()` properly, retain partial data, validate lengths before allocating, and decode UTF-8 only after byte boundaries are handled properly.
