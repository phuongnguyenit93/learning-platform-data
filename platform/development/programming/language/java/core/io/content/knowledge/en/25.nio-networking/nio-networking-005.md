# Designing Length-Prefix or Delimiter Framing in Java NIO Networking

## 1. Why Does TCP Need Framing?

`SocketChannel` in Java NIO sends and receives a TCP **byte stream**. TCP does not preserve application message boundaries: a single `write()` may be read across multiple `read()` calls, and a single `read()` may contain bytes from multiple `write()` calls.

Suppose an application sends two messages `"HELLO"` and `"WORLD"`. The receiver might receive chunks `"HEL"`, `"LOWOR"`, `"LD"`, or receive `"HELLOWORLD"` all at once. Neither split violates the TCP contract. Therefore, a program **cannot** rely on each `read()` to identify one message.

**Message framing** is an application-layer format that delimits individual messages (frames) on a byte stream. Two common approaches are:

- **Length-prefix**: place length information in a header, then send that exact number of payload bytes.
- **Delimiter-based**: terminate each payload with a special byte sequence, such as LF (`0x0A`) or CRLF (`0x0D 0x0A`).

This lesson belongs to Java Core I/O → **NIO Networking**, explaining wire-format design, stateful `ByteBuffer` processing, partial reads/writes, EOF, memory limits, testing, and choosing between techniques.

## 2. Distinguishing Layers During Data Transmission

| Term | Role |
| --- | --- |
| Payload | Application content such as UTF-8 strings, JSON, binary bytes |
| Frame | Payload plus boundary information (length header or delimiter) |
| TCP stream | Ordered byte sequence with no message boundaries |
| `SocketChannel.read(ByteBuffer)` | Transfers some bytes from the socket into the buffer on this call |
| `ByteBuffer` | Memory backing and `position`, `limit`, `capacity` pointers |
| TCP segment | Network-layer packaging unit, not identical to an application frame |

Even if localhost testing feels like "one write equals one read", the application must handle splitting, coalescing, and varying arrival timing. The solution is a **decoder that retains state across byte-receive calls**.

## 3. Length-Header Framing

A simple protocol uses **4 leading bytes as a signed big-endian integer** holding the length in **payload bytes**, followed by that exact number of bytes:

```text
+------------------------------+-----------------------+
| length: 4 bytes (big-endian) | payload: length bytes |
+------------------------------+-----------------------+

"CAT" (3 UTF-8 bytes):
  00 00 00 03 | 43 41 54

"HI" (2 UTF-8 bytes):
  00 00 00 02 | 48 49
```

Details to specify explicitly in protocol documentation:

1. How many bytes the header occupies; 4 in this example.
2. Whether the header counts **payload only** or includes the header; this example counts payload only.
3. Endianness; this example uses `ByteOrder.BIG_ENDIAN`.
4. Negative or out-of-bounds lengths are rejected; `length=0` can represent an empty frame.
5. Whether the payload is UTF-8 text, raw binary bytes, or another schema.
6. Policies for EOF mid-header or mid-payload, timeouts, compression, and overall resource limits.

With UTF-8, **Java character count differs from wire byte count**: `String.length()` is not the value to put into the header. Always encode first and use `payload.getBytes(UTF_8).length`.

### 3.1. Encoder (method snippet inside a Java class)

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;

static ByteBuffer encode(String message) {
    byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
    if (bytes.length > 1024) {
        throw new IllegalArgumentException("Payload too large");
    }
    ByteBuffer frame = ByteBuffer.allocate(4 + bytes.length);
    frame.order(ByteOrder.BIG_ENDIAN);
    frame.putInt(bytes.length);
    frame.put(bytes);
    frame.flip();
    return frame;
}
```

This code is an **illustrative method** that must be placed inside a class. After `flip()`, `position=0` and `limit=4+bytes.length` so `SocketChannel.write(frame)` starts sending bytes from the header. If you forget `flip()`, the channel may send zero new bytes.

A 4-byte length is a signed `int` in Java. If you want unsigned lengths or varints, explicitly specify decoding and overflow checks. Never implicitly treat every 4-byte combination as a valid allocation size.

## 4. A Length Decoder Is a State Machine

With length-prefix framing, the decoder has two phases:

```text
WAIT_HEADER (accumulate all 4 bytes)
             |
             v
     check 0 <= N <= MAX
             |
             +-- N = 0 ------> emit empty frame ----+
             |                                      |
             v                                      |
WAIT_BODY (accumulate exact N bytes)                |
             |                                      |
             +---- emit payload --------------------+
             |
             v
         next WAIT_HEADER
```

Never assume the 4-byte header arrives in a single `read()`. For example, one `read` might contain only 1 header byte, the next 3 bytes, and the following one the payload. Calling `getInt()` before 4 bytes have arrived can throw `BufferUnderflowException`. Likewise, one `read` does not guarantee receiving all `N` payload bytes.

After emitting a frame, the decoder must **continue processing remaining bytes in the same chunk**: a single `read()` can contain multiple complete frames plus part of the next frame.

Example of two consecutive frames:

```text
Frame "Hi":  00 00 00 02  48 69
Frame "NIO": 00 00 00 03  4E 49 4F

Stream: [00 00 00 02 48 69 00 00 00 03 4E 49 4F]

Chunk A [00 00 00]            -> missing 1 header byte
Chunk B [02 48 69 00 00]      -> emit "Hi", keep first 2 bytes of second header
Chunk C [00 03 4E 49 4F]      -> emit "NIO"
```

The decoder must keep persistent state **per TCP connection**: header bytes received so far, validated length, and remaining payload bytes needed. Sharing a single state across two independent sockets could mix bytes from both connections into a corrupted message.

### 4.1. Check size limits before allocating

```java
int length = header.getInt(); // header already holds all 4 bytes
if (length < 0 || length > MAX_PAYLOAD_BYTES) {
    throw new IllegalArgumentException("Invalid length: " + length);
}
```

This is illustrative code requiring an appropriate `header` and `MAX_PAYLOAD_BYTES`. Network input **cannot be trusted for direct allocation**. Never do `new byte[length]` before validating length; a peer can send a huge number to exhaust RAM. For compressed data, also cap the decompressed size. Beyond per-frame limits, the application must bound total buffers, connection counts, pending requests, and timeouts.

## 5. Delimiter-Based Framing

For text protocols, you can pick the **LF byte = `0x0A`** as the terminator:

```text
Sent data: red LF blue LF

Bytes on wire:
  72 65 64 0A 62 6C 75 65 0A
  [ red   ]LF [  blue  ] LF
```

The decoder accumulates bytes until LF, emits the portion before LF as one frame, discards the delimiter, and continues. One chunk can contain multiple LFs (multiple frames); an LF can arrive at the start or end of any chunk.

**Pros:** easy to inspect with CLI tools, fits line-based protocols, logs, and text commands; no need to measure payload length up front.

**Limitations:** the delimiter **must not appear unescaped inside payloads**. If a payload can contain LF, you must specify escaping, quoting, or encoding (such as JSON Lines where newlines inside JSON strings are escaped), or use length-prefix framing instead. Do not automatically treat CRLF and LF as equivalent unless the protocol specifies it.

### 5.1. CRLF and multi-byte delimiters

A `CRLF` delimiter has two bytes: `0x0D 0x0A`. If one chunk ends at CR and the next begins with LF, searching for CRLF within **each individual chunk** will miss the message boundary. The parser must hold the pending CR byte or use a streaming delimiter matcher. For longer delimiters, use a state machine/KMP matcher tracking the matched prefix length.

### 5.2. Line length limits

If the sender never sends LF, the decoder cannot emit a frame and accumulated data grows indefinitely. Enforce `MAX_LINE_BYTES`, check before appending new bytes, enforce timeouts, and define a disconnect policy on violation. Two consecutive LFs can represent an empty frame; accept or reject according to the protocol contract.

## 6. Comparing Length-Prefix and Delimiter Framing

| Criterion | Length-prefix | Delimiter |
| --- | --- | --- |
| Boundary detection | Header + exact N payload bytes | Search for delimiter sequence |
| Arbitrary binary payloads | Easy to support | Must escape occurrences of delimiter |
| Human-readable text inspection | Binary header is inconvenient to read | Easy to inspect in a terminal |
| Knowing payload length | Must know up front or use streaming/chunked strategy | Not needed in advance |
| Decoder | Accumulate header then body | Delimiter matcher across chunks |
| Major risks | Forged header, negative/oversized length, wrong endianness | Forgotten escaping, missing delimiter, overly long lines |
| Frame split across reads | Must retain state | Must retain state |
| Multiple frames in one read | Loop parsing to consume entire chunk | Loop scanning to consume entire chunk |
| EOF mid-frame | Incomplete header/body is an error under strict protocols | Line without delimiter: depends on policy |
| Typical applications | RPC, Protobuf, binary protocols | Line protocols, text commands, JSON Lines |

Hybrids are also possible: a length/type header whose payload contains newline-delimited text. Choose based on data and contract format; no single technique is universally best for every system.

## 7. Standalone Java 17+ Example: Decoding Split or Coalesced Data

The following program **simulates socket read results** by splitting a byte stream into arbitrary chunks. The length-prefix decoder manages a 4-byte header and payload, while the delimiter decoder uses LF; both retain state across calls. This is a deterministic test independent of network timing.

Create file `FramingDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class FramingDemo {
    static final int MAX_BYTES = 1024;

    static byte[] encodeLengthFrame(String text) {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        if (data.length > MAX_BYTES) {
            throw new IllegalArgumentException("Too long");
        }
        ByteBuffer frame = ByteBuffer.allocate(4 + data.length);
        frame.order(ByteOrder.BIG_ENDIAN);
        frame.putInt(data.length);
        frame.put(data);
        return frame.array();
    }

    static class LengthDecoder {
        private final ByteBuffer header =
                ByteBuffer.allocate(4).order(ByteOrder.BIG_ENDIAN);
        private byte[] body;
        private int used;

        List<String> accept(byte[] chunk) {
            List<String> messages = new ArrayList<>();

            for (byte b : chunk) {
                if (body == null) {
                    header.put(b);
                    if (!header.hasRemaining()) {
                        header.flip();
                        int length = header.getInt();
                        header.clear();

                        if (length < 0 || length > MAX_BYTES) {
                            throw new IllegalArgumentException("Bad length");
                        }
                        if (length == 0) {
                            messages.add("");
                        } else {
                            body = new byte[length];
                            used = 0;
                        }
                    }
                } else {
                    body[used++] = b;
                    if (used == body.length) {
                        messages.add(new String(
                                body, StandardCharsets.UTF_8));
                        body = null;
                        used = 0;
                    }
                }
            }
            return messages;
        }

        void endOfInput() throws EOFException {
            if (header.position() != 0 || body != null) {
                throw new EOFException("Incomplete length frame");
            }
        }
    }

    static class LineDecoder {
        private final ByteArrayOutputStream pending =
                new ByteArrayOutputStream();

        List<String> accept(byte[] chunk) {
            List<String> messages = new ArrayList<>();
            for (byte b : chunk) {
                if (b == 10) { // LF
                    messages.add(new String(
                            pending.toByteArray(), StandardCharsets.UTF_8));
                    pending.reset();
                } else {
                    if (pending.size() >= MAX_BYTES) {
                        throw new IllegalArgumentException("Line too long");
                    }
                    pending.write(b);
                }
            }
            return messages;
        }

        void endOfInput() throws EOFException {
            if (pending.size() != 0) {
                throw new EOFException("Missing final LF");
            }
        }
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream stream = new ByteArrayOutputStream();
        stream.writeBytes(encodeLengthFrame("Hi"));
        stream.writeBytes(encodeLengthFrame("NIO"));
        byte[] wire = stream.toByteArray();

        LengthDecoder length = new LengthDecoder();
        System.out.println("length 1: " +
                length.accept(Arrays.copyOfRange(wire, 0, 3)));
        System.out.println("length 2: " +
                length.accept(Arrays.copyOfRange(wire, 3, 8)));
        System.out.println("length 3: " +
                length.accept(Arrays.copyOfRange(wire, 8, wire.length)));
        length.endOfInput();

        byte[] lines = ("red" + (char) 10 + "blue" + (char) 10)
                .getBytes(StandardCharsets.UTF_8);
        LineDecoder line = new LineDecoder();
        System.out.println("line 1: " +
                line.accept(Arrays.copyOfRange(lines, 0, 2)));
        System.out.println("line 2: " +
                line.accept(Arrays.copyOfRange(lines, 2, 6)));
        System.out.println("line 3: " +
                line.accept(Arrays.copyOfRange(lines, 6, lines.length)));
        line.endOfInput();
    }
}
```

Compile/run with JDK 17 or newer:

```bash
javac FramingDemo.java
java FramingDemo
```

Output:

```text
length 1: []
length 2: [Hi]
length 3: [NIO]
line 1: []
line 2: [red]
line 3: [blue]
```

**Explanation:**

1. The first length-prefix chunk only has 3 header bytes, so nothing can be emitted yet.
2. The second chunk contains the fourth header byte, the payload `Hi`, and the first 2 bytes of the next header. The decoder emits `Hi` and retains the partial header state.
3. The final chunk completes the second header and the three bytes `NIO`, emitting `NIO`.
4. With the delimiter decoder, the first two bytes are `re`. The next chunk is `d`, LF, `bl`; the decoder emits `red` and retains `bl`. The final chunk is `ue`, LF, so it emits `blue`.
5. `endOfInput()` verifies EOF occurred on a frame boundary. If a header/body or line is incomplete, this example throws `EOFException`.

The demo decoder uses `new String(bytes, UTF_8)`, which may replace invalid UTF-8 bytes. If the protocol *strictly* requires valid UTF-8, use `CharsetDecoder` with `CodingErrorAction.REPORT`. For high performance, the per-byte loop can be replaced with a parser reading directly from `ByteBuffer`, while preserving the same framing invariants.

## 8. Integrating with `SocketChannel` and `ByteBuffer`

Real Java NIO code must distinguish three return values from `read()`:

- `n > 0`: `n` new bytes arrived; feed **this exact slice** to the decoder.
- `n == 0`: no new bytes in this call, typical when a non-blocking socket is not ready; do not emit and do not treat as EOF.
- `n == -1`: input stream ended; call `decoder.endOfInput()` to check for partial frames and finish reading per policy.
- `IOException`: I/O error to handle separately; never convert into an empty frame.

Illustrative handler skeleton **inside an application handler**; `socket`, `buffer`, `decoder`, and `handleMessage` must be defined outside the snippet:

```java
int n = socket.read(buffer);

if (n > 0) {
    buffer.flip();
    byte[] chunk = new byte[buffer.remaining()];
    buffer.get(chunk);

    for (String message : decoder.accept(chunk)) {
        handleMessage(message);
    }
    buffer.clear();
} else if (n == 0) {
    // Non-blocking: return to Selector/event loop to wait further.
} else {
    decoder.endOfInput();
    // Finish receiving, close, or half-close per protocol.
}
```

This example assumes `buffer` is prepared to receive data from the prior read. In a real application, handle callback errors, byte limits, and resource closing states.

**Two different buffer-management patterns:**

- **The decoder owns pending bytes internally**, like `LengthDecoder` in the example: after feeding all new bytes into the decoder, you can call `buffer.clear()`. `clear()` only resets `position/limit` and does not erase bytes.
- **The decoder keeps partial data inside the read buffer itself**: after switching to read mode with `flip()`, the parser consumes complete frames and then calls `compact()` to retain trailing incomplete bytes; never call `clear()` if a partial frame remains.

Do not mix the two approaches, to avoid losing data or re-reading stale bytes. Each connection keeps its own decoder and read buffer.

### 8.1. Selector does not determine message boundaries

`SelectionKey.isReadable()` only indicates readability; it **does not promise** that `read()` will receive a full frame, or that each ready notification contains one message. In the event loop:

```text
Selector picks readable key
           |
       channel.read(buffer)
         /      |       \
       n>0     n=0     n=-1
        |       |        |
    feed     wait for   EOF -> finalize decoder
   decoder    event     and close per policy
        |
   emit 0..N frames
```

If `read` returns `0`, do not loop continuously in a `while` loop without waiting: that causes a busy loop and wastes CPU. Return control to the selector/event loop and hold pending state until the next round.

## 9. The Write Side Must Handle Partial Writes

Just like `read()`, `SocketChannel.write(ByteBuffer)` may process **fewer bytes than remain**, especially in non-blocking mode. This must never alter frame ordering:

```java
ByteBuffer frame = encode("Hello");
int written = socket.write(frame);
// If frame.hasRemaining(), the frame is not finished sending yet.
```

This is a snippet inside a method with `socket` and `encode`. When bytes remain in the frame, retain that exact buffer at its current `position` to keep writing. Calling `clear()` or immediately sending the next frame can interleave headers/payloads or lose bytes.

A common design is an **outbound queue** holding a `Deque<ByteBuffer>`, where each element is a flipped frame ready for reading. On `OP_WRITE`, write the head element until its bytes finish or the socket temporarily stops accepting more:

```java
while (!outbound.isEmpty()) {
    ByteBuffer head = outbound.peek();
    int written = socket.write(head);

    if (head.hasRemaining()) {
        // Bytes remain; keep head at the front of the queue and wait for OP_WRITE.
        break;
    }
    outbound.remove();

    if (written == 0) {
        break;
    }
}
```

This is an illustrative snippet inside a handler that already has `SocketChannel socket` and `Deque<ByteBuffer> outbound`. In the event loop, register `OP_WRITE` only when pending bytes exist and clear this interest when the queue empties to avoid continuous writable notifications from the selector. Bound total outbound bytes to handle slow-reading clients (backpressure).

**`write()==0` is not EOF.** It means this write attempt transferred zero bytes; with a non-blocking socket you must wait for an appropriate readiness event.

## 10. EOF, Timeouts, and Truncated Messages

When `read()` returns `-1`, the protocol must decide whether currently buffered data forms a valid frame or is incomplete.

| State at EOF | Interpretation under strict protocol |
| --- | --- |
| Length decoder waiting for a new header, no leftover bytes | Normal termination |
| Header received 1–3 of 4 bytes | Truncated header |
| Length header N received, payload has K bytes with K < N | Truncated payload |
| Delimiter decoder has no pending bytes | Normal termination |
| Delimiter decoder has pending bytes without delimiter | Missing delimiter, if protocol requires LF termination |
| Delimiter protocol allows final line without LF | Can emit last line, but must document this exception explicitly |

Not every protocol allows EOF to substitute for a delimiter. With Unix-style lines, a final line without LF may be accepted; if framing strictly requires LF, it must error. **Both sides must agree**.

Beyond EOF, there are timeout policies: a client might send a header and hold the connection open forever without sending the payload; the decoder needs a per-frame deadline, connection limits, and slow-operation cancellation. TCP half-close means the sender ending output does not necessarily mean the receiver also closed; applications should distinguish data directions.

## 11. UTF-8 Data and Delimiters

If sending `"Tiếng Việt"` with length-prefix framing, the header holds the number of **UTF-8 bytes**, not the Java character count. A multi-byte character can be split across two socket reads; the decoder should wait for the complete payload before decoding, or use a streaming `CharsetDecoder`.

With an LF `0x0A` delimiter, scanning bytes first and then decoding the full frame is simple if the protocol chooses UTF-8 and forbids raw LF inside payloads. For JSON Lines, newlines inside string fields must be escaped as valid text (e.g., backslash+n) rather than embedded as raw LF bytes.

If the delimiter is a multi-byte sequence such as CRLF, part of the delimiter may sit at the end of one read buffer and the rest at the start of the next. When scanning chunk by chunk, use a stateful matcher or retain a long enough tail to join with the next chunk.

If binary data can contain arbitrary byte values, **length-prefix is usually simpler** than a delimiter scheme that has to escape every occurrence of the separator.

## 12. Safe Handling and Resource Limits

**For length-prefix:**

- Reject negative lengths or lengths exceeding `MAX_FRAME_BYTES` before allocating.
- Limit total queued frames, frame receive duration, and total bytes in queues.
- If compression is used, bound the decompressed size as well.
- If a structured schema is used, validate version, type, and payload format before use.
- Ensure Java char length is never mistaken for byte count.

**For delimiter:**

- Accumulate at most `MAX_LINE_BYTES` before the delimiter, even if the peer never sends one.
- If the delimiter can appear in payloads, escape/quote per format or choose another framing method.
- Specify whether CRLF and LF may coexist.
- Specify empty frames, trailing delimiters, and EOF without delimiter.

**For both:**

- Independent decoder per connection.
- Timeouts, idle timeouts, close policies, and appropriate exception logging.
- No busy-loops when read or write returns 0.
- Manage inbound/outbound backpressure.
- Do not trust network input merely because frame boundaries were parsed: framing **does not** authenticate identity, encrypt data, or ensure payload safety.

## 13. Testing at Every Chunk Split Point

Because TCP read boundaries are arbitrary, write tests feeding **the exact same valid byte stream** into the decoder under many chunking patterns:

1. One byte at a time.
2. All bytes in a single chunk.
3. Split between each byte of the length header.
4. Split between header and payload.
5. Split inside a multi-byte UTF-8 character.
6. A chunk containing multiple complete frames plus part of the next frame.
7. Split between CR and LF of a CRLF delimiter.
8. EOF while header or payload is incomplete.
9. Negative header, oversized header, missing delimiter, overly long line.

Desired invariant:

```text
decode(allBytes as one chunk)
  == decode(same bytes split into arbitrary chunks)
```

Here `decode` compares the frame list **with identical content and order**, assuming a valid byte stream and identical initial state. For invalid streams, also verify the error type and that partial data is never emitted.

Property-based testing/fuzzing is very helpful: generate random frame sequences with the encoder, concatenate into a stream, split randomly into chunks, and verify the decoder produces the exact original frames. Such tests catch bugs missed by "one write, one read" tests.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming one `write` equals one `read` | Frames split or coalesced incorrectly | Stateful streaming parser |
| Reading once and calling `getInt()` immediately | Missing header bytes | Wait for all 4 bytes |
| Header uses `String.length()` | Wrong UTF-8 length | Count bytes after encoding |
| Encoder/decoder use different endianness | Length misinterpreted | Choose BIG_ENDIAN and test wire bytes |
| Allocating unboundedly from network length | OutOfMemory/DoS | Validate before allocation |
| Emitting only one frame per chunk | Remaining frames skipped/delayed | Loop until chunk is consumed |
| Not retaining partial frame state | Lost header/payload across reads | `compact()` or stateful decoder |
| Delimiter appears inside payload | Premature split | Escaping/encoding/length-prefix |
| No byte limit while waiting for delimiter | Unbounded memory growth | MAX_LINE_BYTES and deadline |
| Searching CRLF only within each chunk | Split delimiter missed | Streaming delimiter matcher |
| Treating `read()==0` as EOF | Erroneous disconnect | Only `-1` is EOF |
| Looping tightly on `write()==0` | Busy CPU | `OP_WRITE`, queue, and backpressure |
| Calling `clear()` before keeping leftover bytes | Partial frame lost | `compact()` or state machine |
| Emitting incomplete frame on EOF | Truncated data | Report truncated frame under strict protocol |

## 15. Self-Check

**1.** A client calls `write` twice for two messages, and the server receives one `read` containing both. Is TCP broken?  
**Answer:** No. Application-layer framing must separate the two messages.

**2.** The length header is 4 bytes, and a read returns only 2 bytes. Can the decoder call `getInt()`?  
**Answer:** No. Wait for all 4 bytes before reading the length.

**3.** A payload is 5 bytes long, and only 3 arrive first. Should it be emitted immediately?  
**Answer:** No. Keep the 3 bytes and wait for the next 2 bytes, or report truncation on EOF.

**4.** A chunk contains frame A, frame B, and the first two bytes of frame C. What does the decoder do?  
**Answer:** Emit A and B, and keep the first two bytes of C.

**5.** A line protocol uses LF, yet user data contains newlines. Can it be sent raw?  
**Answer:** Not without escaping/quoting; alternatively switch to length-prefix.

**6.** CRLF is split across two chunks at CR and LF. What does the parser need?  
**Answer:** Retain incomplete delimiter state across chunks.

**7.** A peer sends a length header of 2,000,000,000 bytes. Should you allocate immediately?  
**Answer:** No. Validate against limits and reject if exceeded.

**8.** `SocketChannel.write` returns 0 while the frame still has bytes. Can you send the next frame ahead of it?  
**Answer:** No. Keep the head frame in the queue and wait for writability.

**9.** EOF arrives when the length decoder holds only 3 bytes of a header. Can it be treated as an empty message?  
**Answer:** No. Under strict framing this is a truncated header.

## 16. Implementation Checklist

- Finalize the wire format: byte order, header length, length semantics, charset/delimiter, maximums, empty frames, versioning.
- Decoder maintains state across `read` calls and emits 0..N frames per chunk.
- Producer handles partial `write` using `ByteBuffer.position()` and a queue.
- NIO event loop distinguishes `read>0`, `read==0`, `read==-1`.
- Define EOF/timeout behavior when a frame is incomplete.
- Bound frame/line sizes, total queues, connection counts, and wait times.
- Test splitting/coalescing frames at every boundary and test invalid inputs.
- Decode UTF-8 only when full bytes arrive, or use a streaming decoder; use strict validation when required.
- Benchmark performance and backpressure under load rather than relying on localhost behavior.

## Official API References

- Java SE 21 — `SocketChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html
- Java SE 21 — `ReadableByteChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ReadableByteChannel.html
- Java SE 21 — `WritableByteChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/WritableByteChannel.html
- Java SE 21 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 21 — `Selector`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html
- Java SE 21 — `CharsetDecoder`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html
