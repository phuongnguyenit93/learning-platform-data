# Retaining Unprocessed Data When a Message Spans Multiple Reads

## 1. Objective and Problem Statement

A Java application uses `SocketChannel` to receive TCP data. The sender packs two messages in order. The receiver calls `read(ByteBuffer)`, but may receive **half a header**, **a partial payload**, or **two messages plus part of the next message** in the same read. If the decoder only tries to parse the newly received portion and then calls `clear()`, bytes that are not yet sufficient to form a complete message will disappear from the processing state.

This lesson guides you on retaining **bytes that have been received but not yet consumed into a complete message** across multiple read calls in Java NIO. The focus is on `ByteBuffer`, `SocketChannel`, parser state, and framing mechanisms. This lesson belongs to the **Buffers and Channels** group; you do not need to learn the full selector design or other business protocols to understand and implement the principle correctly.

After this lesson, you should be able to:
- Distinguish **a single `read`** from **an application message**, especially over a TCP stream.
- Understand `position`, `limit`, `capacity`, and know how to use `flip()` → parse → `compact()` to retain leftover bytes.
- Handle **incomplete headers**, **incomplete payloads**, **multiple frames in one buffer**, **frames larger than initial capacity**, **EOF mid-frame**, and **`read() == 0`**.
- Write a memory-bounded decoder with per-connection state on your own; without losing, duplicating, or reordering bytes when reading in fragments.
- Verify Java 17+ code using chunks intentionally split across boundaries, then apply the same mechanism to a real `SocketChannel`.

## 2. Why Can a Message Span Multiple Reads?

TCP provides an **ordered byte stream**. It does not promise that one `write` on the sender side corresponds to one `read` on the receiver side. TCP segments, socket buffers, scheduler timing, system load, and `ByteBuffer` size can cause data to arrive at the parser in any valid fragmentation. A single `read` may even contain multiple application messages.

For example, an application defines a message with a four-byte length prefix (big-endian) followed by a UTF-8 payload:

```text
Message A = "CAT":
  00 00 00 03  43 41 54
  [length=3]   [CAT]

Message B = "DOG":
  00 00 00 03  44 4F 47
  [length=3]   [DOG]

Byte stream on the TCP connection:
  00 00 00 03 43 41 54 00 00 00 03 44 4F 47
```

Successive `SocketChannel.read` calls can easily split the stream as follows:

```text
read #1: 00 00
read #2: 00 03 43
read #3: 41 54 00 00 00 03 44
read #4: 4F 47
```

After `read #1`, the parser does not yet have the full 4-byte header. After `read #2`, the parser has the complete header but has only seen 1 byte of payload; it cannot emit `CAT` yet. In `read #3`, the parser gets the remaining 2 bytes of A and part of the header/payload of B. In `read #4`, the parser finally has all of B.

**If you lose the leftover bytes from a read, there is no way to recover those bytes in the next read.** TCP considers them delivered to the application once `read` returns a positive byte count.

A note on scope: this example is a **TCP stream**. UDP preserves individual datagram boundaries, and a small buffer can **truncate** a datagram; UDP does not use the same strategy of retaining "the remainder of a datagram" to receive the rest like TCP. Even so, a business message split across multiple UDP datagrams still requires an application-defined reassembly mechanism.

## 3. Separating Three Levels of State

To design a correct parser, you must distinguish:

1. **Transport input:** bytes that have arrived at the socket and been copied into a buffer by `SocketChannel.read`. A read call can return `n > 0`, `n == 0`, or `-1` (EOF).
2. **Byte accumulator:** bytes that have arrived at the application but are **not yet sufficient to form a frame** or have not yet been consumed by the parser. This is the part that must be retained between reads.
3. **Message parser/consumer:** complete messages whose length has been validated and that have been extracted from the accumulator. From here, the message belongs to application logic, a work queue, or another data structure.

```text
TCP socket
   │
   ▼  channel.read(...), receives 0..N bytes
ByteBuffer in write mode: [old incomplete bytes][new bytes]
   │
   ▼  flip()
ByteBuffer in read mode:  [complete frame][complete frame][incomplete bytes]
   │
   ├── dispatch complete frames to business processing
   │
   ▼  compact()
ByteBuffer in write mode: [incomplete bytes][free space for next receive]
   │
   └── next read appends after the incomplete bytes
```

**Core invariant:** Bytes not yet sufficient to complete a frame must always remain in the accumulator, in the exact order, until enough data arrives or the connection is closed/errors out. Once a frame is dispatched, its bytes must not be dispatched again.

## 4. ByteBuffer: position, limit, capacity, and Mode

A `ByteBuffer` has three important numbers:

- `capacity`: buffer size, immutable over the object's lifetime.
- `position`: index of the next read/write location.
- `limit`: boundary that must not be exceeded when reading/writing.
- `remaining()` = `limit - position`; `hasRemaining()` checks whether there is anything between position and limit.

At all times, the invariant `0 <= position <= limit <= capacity` holds.

When a buffer is newly created:

```java
ByteBuffer buffer = ByteBuffer.allocate(12);
```

Its state is `position=0, limit=12, capacity=12`; we commonly call this **write mode** because we are preparing to insert bytes into the buffer.

Suppose the channel or `put(...)` has just written 7 bytes; the state is `position=7, limit=12`. Calling `flip()` switches to **read mode**: `position=0, limit=7`. When the parser has consumed 5 bytes, `position=5, limit=7`, leaving exactly 2 unprocessed bytes. At this point:

```text
After flip and parse: capacity = 12, limit = 7, position = 5

index:   0   1   2   3   4   5   6   7  ... 11
         [ processed frame   ][X ][Y ][outside read limit]
                               ▲
                            position=5
         ^                               ^
        0                              capacity=12

compact() copies the two bytes X,Y to the beginning:
index:   0   1   2   3   4  ... 11
         [X ][Y ][     writable region     ]
                  ▲
              position=2, limit=12
```

Primary operations:

| API | Effect | Retains unread bytes? |
| --- | --- | --- |
| `flip()` | `limit = position; position = 0`, prepares to read the bytes just written | Yes, only changes pointers |
| `compact()` | Shifts bytes in `[position, limit)` to the start, `position = retained byte count`, `limit = capacity` | **Yes**, this is the default choice when an incomplete frame remains |
| `clear()` | `position = 0; limit = capacity`, prepares to write again from the start | **Does not preserve incomplete byte state**; may overwrite them |
| `rewind()` | `position = 0`, keeps limit, reads again from the start | Can cause already-processed frames to be processed **again** |
| `mark()/reset()` | Temporarily remembers/restores position while parsing | Useful for undoing a header read when payload is incomplete |
| `remaining()` | Number of bytes still readable/writable in the current mode | Just an arithmetic calculation, does not check frame boundaries |

`compact()` **does not clear memory**; it only moves remaining bytes and updates position/limit. `clear()` does not zero-fill the buffer either; the name "clear" only relates to pointer state. Therefore, never treat old bytes outside `[position, limit)` as valid data.

## 5. Key Case: Complete Header, Incomplete Payload

The illustrative protocol specifies that each frame has:

```text
+---------------------+-------------------------------+
| 4-byte signed int   | length bytes of UTF-8 payload |
| big-endian length   | may be 0..MAX_PAYLOAD bytes   |
+---------------------+-------------------------------+
```

The sender must write **the exact byte length**, not `String.length()`. The receiver must validate `0 <= length <= MAX_PAYLOAD` *before* allocating or retaining the payload.

Suppose the buffer currently holds:

```text
00 00 00 05  48 45
[length=5]  "HE" (missing "LLO")
```

After `flip()`, the parser sees all 4 header bytes and calls `getInt()`. However, `remaining() == 2 < 5`, meaning the payload is incomplete. If it simply `break`s and calls `compact()` at this point, **the header has already been consumed**, the two bytes `HE` are shifted to the front, and next time the parser will read `HE...` as a new header: the protocol loses synchronization.

The right way:
1. Before reading the length, call `mark()` at the start of the frame.
2. Read `length` and validate it.
3. If the payload is incomplete, call `reset()` so position moves **back to the start of the header**.
4. Exit the parse loop; call `compact()` to retain **both the header and the partial payload**.
5. The next read appends after the retained bytes; retry parsing from the start of the frame.

Example logic in read mode:

```java
while (buffer.remaining() >= Integer.BYTES) {
    buffer.mark();
    int length = buffer.getInt();
    if (length < 0 || length > MAX_PAYLOAD) {
        throw new IOException("Invalid frame length");
    }
    if (buffer.remaining() < length) {
        buffer.reset(); // both header and partial payload remain pending
        break;
    }
    byte[] payload = new byte[length];
    buffer.get(payload);
    handleFrame(payload);
}
buffer.compact();
```

This is an **illustrative code snippet**; it assumes `ByteBuffer buffer`, constant `MAX_PAYLOAD`, `handleFrame`, and `java.io.IOException` already exist. The loop condition protects `getInt()` from reading when fewer than 4 bytes are available; omitting that check could trigger a `BufferUnderflowException`.

### Why Must We Use a `while` Loop Instead of `if`?

A single `read` can contain **multiple complete frames**, such as `[len=1]["A"][len=1]["B"][len=2]["OK"]`. A `while` loop processes all complete frames first, and only then retains the incomplete tail. If you only process one frame per callback and stop parsing what is already in the buffer, the program can **stall on messages** even though all bytes have arrived, because no new read event will arrive to wake the parser.

## 6. Designing an Accumulator That Persists Across Multiple Feeds

There are two common approaches:

- **One stateful ByteBuffer per connection:** the channel reads directly into the buffer, and the parser `flip/compact`s that same buffer. Easy to optimize, but requires enough capacity for the largest frame or a growth mechanism.
- **One I/O read buffer and one parser accumulator:** the channel reads into the I/O buffer, then transfers bytes to a decoder that holds state across callbacks. Clear ownership; may incur one extra copy, useful for deterministic unit tests.

The example in section 7 uses the second approach to simulate chunked reads, avoiding dependence on how the OS actually splits the TCP stream. The example in section 9 uses the first approach on a real `SocketChannel`.

**Never create a new accumulator on every read.** If each callback executes `ByteBuffer.allocate(...)`, parses, and discards the buffer, any incomplete header/payload is lost as soon as the callback finishes. For a multi-connection server, each connection needs independent state; never share a single mutable `ByteBuffer` across peers.

## 7. Runnable Java 17+: Parser Remains Correct With Chunks Intentionally Split Mid-Frame

The program below generates wire bytes using `DataOutputStream.writeInt`, then feeds those bytes into `FrameDecoder` across 7 chunks of varying sizes. It demonstrates in full:
- A 4-byte header can be split across multiple chunks.
- A payload can be split across multiple chunks.
- A single chunk can contain the end of the previous frame and the start of the next frame.
- `compact()` retains all unconsumed bytes.
- An initial buffer of only 8 bytes can **grow** in a bounded manner when a valid frame does not fit yet.

Save with the exact filename `FrameAcrossReadsDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class FrameAcrossReadsDemo {
    private static final int MAX_PAYLOAD = 64;

    static final class FrameDecoder {
        private ByteBuffer pending = ByteBuffer.allocate(8); // write mode

        void accept(byte[] chunk) {
            int offset = 0;
            while (offset < chunk.length) {
                if (!pending.hasRemaining()) grow();
                int count = Math.min(pending.remaining(), chunk.length - offset);
                pending.put(chunk, offset, count);
                offset += count;
                parseAvailable();
            }
        }

        private void parseAvailable() {
            pending.flip(); // write mode -> read mode
            while (pending.remaining() >= Integer.BYTES) {
                pending.mark(); // remember where this frame starts
                int length = pending.getInt();
                if (length < 0 || length > MAX_PAYLOAD) {
                    throw new IllegalArgumentException("invalid frame length");
                }
                if (pending.remaining() < length) {
                    pending.reset(); // restore header for next read
                    break;
                }
                byte[] payload = new byte[length];
                pending.get(payload);
                System.out.println("FRAME " + new String(payload, StandardCharsets.UTF_8));
            }
            pending.compact(); // keep unconsumed bytes, return to write mode
        }

        private void grow() {
            int maximum = MAX_PAYLOAD + Integer.BYTES;
            if (pending.capacity() >= maximum) {
                throw new IllegalStateException("frame exceeds buffer policy");
            }
            ByteBuffer larger = ByteBuffer.allocate(
                    Math.min(pending.capacity() * 2, maximum));
            pending.flip();
            larger.put(pending);
            pending = larger;
        }

        int retainedBytes() { return pending.position(); }

        void endOfStream() {
            pending.flip();
            if (pending.hasRemaining()) {
                throw new IllegalStateException("truncated frame at EOF");
            }
            System.out.println("EOF complete");
        }
    }

    private static void writeFrame(DataOutputStream out, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            writeFrame(out, "A");
            writeFrame(out, "HELLO");
            writeFrame(out, "OK");
        }
        byte[] wire = bytes.toByteArray(); // 5 + 9 + 6 = 20 bytes
        int[] chunkSizes = {2, 1, 4, 2, 5, 1, 5};
        FrameDecoder decoder = new FrameDecoder();
        int offset = 0;
        for (int size : chunkSizes) {
            byte[] chunk = Arrays.copyOfRange(wire, offset, offset + size);
            decoder.accept(chunk);
            offset += size;
            System.out.println("chunk=" + size
                    + " retained=" + decoder.retainedBytes());
        }
        if (offset != wire.length) throw new AssertionError("bad test chunks");
        decoder.endOfStream();
    }
}
```

Compile and run with Java 17 or later:

```bash
javac FrameAcrossReadsDemo.java
java FrameAcrossReadsDemo
```

Verified stdout:

```text
chunk=2 retained=2
chunk=1 retained=3
FRAME A
chunk=4 retained=2
chunk=2 retained=4
FRAME HELLO
chunk=5 retained=0
chunk=1 retained=1
FRAME OK
chunk=5 retained=0
EOF complete
```

### Explaining the Output

The wire format has 3 frames: `A` takes 4+1=5 bytes, `HELLO` takes 4+5=9 bytes, `OK` takes 4+2=6 bytes, totaling **20 bytes**.

- **2-byte chunk, then 1-byte chunk:** the parser only has 2 and then 3 bytes, so it does not read the incomplete header. `retained=3`.
- **4-byte chunk:** 7 bytes total; the parser extracts frame `A` (5 bytes), leaving 2 bytes belonging to the `HELLO` header. `compact()` retains those exact 2 bytes.
- **2-byte chunk:** the `HELLO` header is complete (4 bytes), but the 5-byte payload is still missing; the parser calls `reset()` back to the start of the header. `retained=4`.
- **5-byte chunk:** the program needs to expand the buffer from 8 to 16 bytes when the partial header+payload does not fit; it then receives all 9 bytes and emits `FRAME HELLO`. No bytes are lost.
- **1-byte chunk:** retains the first 1 byte of the `OK` header.
- **5-byte chunk:** completes frame `OK`, emits the message, and the buffer has no pending bytes left.
- **EOF:** no pending header/payload remains → `EOF complete`.

An important characteristic of the decoder: after each `accept`, `pending` always returns to **write mode**; `position()` at that moment represents **the number of unconsumed bytes currently retained**, not the total bytes received since the start of the connection.

### Limitations of the Example

This program simulates splitting reads into chunks, so the result is deterministic. It does **not** open a real TCP connection; section 9 demonstrates applying the same idea to a socket channel. The demo uses ASCII for stable stdout, while the wire length rule remains **UTF-8 byte count**. Calling `endOfStream()` is the final operation in the decoder's lifecycle; after flipping the buffer to check for EOF, do not call `accept` again on that same decoder.

## 8. When a Frame Is Larger Than the Initial Buffer: Bounded Growth

An 8-byte buffer cannot hold both a 4-byte header and a 5-byte `HELLO` payload at the same time. If the parser only calls `compact()`, sees `position == capacity`, and calls `channel.read(buffer)` again, the buffer **has no space left to write**. With a blocking channel, `read` when the buffer has no remaining space can return 0, making the application think "the network stopped sending" even though the parser itself is holding an incomplete frame.

There are three valid strategies:

1. **Allocate a buffer large enough for the maximum frame:** if `MAX_PAYLOAD = 64`, allocate at least `4 + 64 = 68` bytes. Simple, but wastes memory across many connections if the max is high.
2. **Grow the buffer up to a configured limit:** like `FrameDecoder.grow()`; transfer retained bytes to the new buffer using `flip()` then `put(...)`. Do not grow unboundedly and do not read lengths outside the protocol.
3. **Separate header/payload state machine parser:** read the full header, validate length, allocate a bounded payload buffer; when payload is incomplete, continue filling the remainder, and dispatch only once complete. This fits cases where you want to handle large frames without forcing a single accumulator to continuously hold both header and payload.

In every strategy, **a frame size limit is mandatory**, especially with untrusted sources. A header stating `2_000_000_000` must never cause the server to immediately allocate a 2 GB array or accumulate indefinitely. Reject early when length is negative, exceeds max, violates protocol version, or exceeds the connection's quota.

Avoid computing `length + 4` before validating when `length` comes from the network; integer overflow can turn a very large positive number into a wrong value. Check `0 <= length <= MAX_PAYLOAD` first, and only then add the header size.

## 9. Runnable Java 17+: Reading From a Real SocketChannel

The standalone program below creates a TCP listener on `127.0.0.1` and has an in-process client send two frames. The parser uses **a single `ByteBuffer` that persists across the `read` loop**, rather than decoding each read call in isolation. Because the example sets `MAX_FRAME = 60` and the buffer to `MAX_FRAME + 4`, any valid frame can always be accumulated in full.

Save with the exact filename `SocketChannelFrameDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;

public class SocketChannelFrameDemo {
    private static final int MAX_FRAME = 60;

    private static byte[] encode(String... messages) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            for (String message : messages) {
                byte[] payload = message.getBytes(StandardCharsets.UTF_8);
                out.writeInt(payload.length);
                out.write(payload);
            }
        }
        return bytes.toByteArray();
    }

    private static void parse(ByteBuffer buffer) throws IOException {
        buffer.flip();
        while (buffer.remaining() >= Integer.BYTES) {
            buffer.mark();
            int length = buffer.getInt();
            if (length < 0 || length > MAX_FRAME) {
                throw new IOException("Invalid frame length: " + length);
            }
            if (buffer.remaining() < length) {
                buffer.reset();
                break;
            }
            byte[] payload = new byte[length];
            buffer.get(payload);
            System.out.println("message=" +
                    new String(payload, StandardCharsets.UTF_8));
        }
        buffer.compact();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            try (SocketChannel sender = SocketChannel.open(
                         new InetSocketAddress(loopback,
                                 ((InetSocketAddress) listener.getLocalAddress()).getPort()));
                 SocketChannel receiver = listener.accept()) {

                ByteBuffer outgoing = ByteBuffer.wrap(encode("cat", "elephant"));
                while (outgoing.hasRemaining()) sender.write(outgoing);
                sender.shutdownOutput();

                ByteBuffer incoming = ByteBuffer.allocate(MAX_FRAME + Integer.BYTES);
                for (;;) {
                    int n = receiver.read(incoming);
                    if (n == -1) break;
                    if (n == 0) continue; // relevant for nonblocking channels
                    parse(incoming); // retains incomplete header/body
                }
                incoming.flip();
                if (incoming.hasRemaining()) {
                    throw new IOException("Truncated frame at EOF");
                }
                System.out.println("EOF complete");
            }
        }
    }
}
```

Compile and run:

```bash
javac SocketChannelFrameDemo.java
java SocketChannelFrameDemo
```

Typical stdout on loopback when sending/receiving succeeds:

```text
message=cat
message=elephant
EOF complete
```

**Why does this code work across arbitrary TCP fragmentation?** A single `read` might fetch both frames at once, or only a few bytes, but both cases go through `parse(incoming)`. After `parse`, `compact()` shifts any incomplete header/payload to the front and preserves the write position for the next receive. After the sender calls `shutdownOutput()`, the receiver keeps reading until `-1` and then verifies no partial frame remains. If the network/socket fails, the code throws `IOException`; TCP does not guarantee the application will always complete every frame when a connection is cut.

For production code, you need reasonable timeouts, thread management, connection limits, malformed payload handling, and timeouts for retaining partial frames. This example uses loopback solely to verify the principle.

### Why Use `sender.shutdownOutput()` Instead of Waiting for "No More Bytes"?

`shutdownOutput()` signals the end of the **send direction** of TCP, allowing the receiver to observe EOF after receiving all in-flight bytes. Merely observing that `read` temporarily has no data does **not** prove the sender has finished a message; the receiver must rely on the **length-prefix** to know when a message is complete, and use EOF only to know that the send stream has ended.

## 10. Handling `read()`, EOF, and Non-Blocking NIO

`SocketChannel.read(ByteBuffer)` can return:

| Result | Meaning | Action |
| --- | --- | --- |
| `n > 0` | Placed `n` new bytes into the buffer, advancing `position` | `flip()`, parse all complete frames, `compact()` to retain the remainder |
| `n == 0` | No bytes were placed into the buffer; common with non-blocking channels | Do not parse a new message just because of 0; wait for the next readiness event or handle a full buffer |
| `n == -1` | The read side reached EOF | Process any remaining complete frames, then check **whether incomplete bytes remain**; close/cleanup |

In blocking mode with writable space in `ByteBuffer`, `SocketChannel.read` normally blocks until at least 1 byte arrives or EOF/error occurs. In non-blocking mode, `read` can return `0` immediately when no bytes are available. A `SelectionKey` reporting `OP_READ` can be triggered by data, EOF, or an error, so **readiness is only a signal to check**, not a guarantee of receiving a complete frame.

### Clean EOF vs. Mid-Frame EOF

If no unprocessed bytes remain in the buffer at the end, the stream ended **cleanly at the framing level**. If only 1–3 header bytes remain, or a full header with an incomplete payload remains, that is a **truncated frame**. Do not silently drop it and report success. You can throw `IOException("Truncated frame at EOF")` and close the connection.

If the protocol allows zero-length frames, the header `00 00 00 00` is still a **complete frame**. Do not confuse a 0-length frame with EOF: EOF is a channel state, not a frame. In a specific application, you may require length to be greater than 0 and reject empty frames; that is a business choice.

### Non-Blocking and Selector

In a multi-connection server:

```text
key A -> SocketChannel A + FrameDecoder A
key B -> SocketChannel B + FrameDecoder B
key C -> SocketChannel C + FrameDecoder C
```

Each connection has its own `SelectionKey.attachment()` or state map; when a key is readable, read until the channel returns 0, EOF, or the event loop's per-turn work budget is reached. Do not create a new decoder on each event. Do not copy bytes from connection A into B's accumulator.

**Do not write a busy loop** `while (channel.read(buffer) == 0) { }` because it burns CPU. Rely on `selector.select()` to wait and only keep `OP_READ` enabled when there is capacity to receive/parse; if downstream processing is overloaded, deliberately adjust read interest/backpressure.

## 11. Using Separate Buffers for I/O and the Accumulator

Some architectures have the channel read into a small I/O buffer, then transfer bytes to a long-lived decoder. The correct flow:

```text
channel.read(ioBuffer) → ioBuffer.flip()
→ decoder.accept(the bytes read)
→ ioBuffer.clear() for the next read

decoder.accept:
  append to THAT connection's pending buffer
  parse all complete frames
  compact to retain incomplete bytes
```

When using a temporary I/O buffer, calling `clear()` after transferring bytes to the decoder is valid because **the decoder now owns the unprocessed bytes**. Conversely, if the I/O buffer **is also** the accumulator, you must call `compact()` after parsing and never `clear()` while leftovers remain. Both designs are valid as long as ownership and lifetime are clearly defined.

A method snippet illustrating how to transfer bytes to `FrameAcrossReadsDemo.FrameDecoder` from section 7:

```java
static void receive(SocketChannel channel,
                    FrameAcrossReadsDemo.FrameDecoder decoder)
        throws IOException {
    ByteBuffer io = ByteBuffer.allocate(1024);
    for (;;) {
        int n = channel.read(io);
        if (n == -1) {
            decoder.endOfStream();
            return;
        }
        if (n == 0) continue;
        io.flip();
        byte[] bytes = new byte[io.remaining()];
        io.get(bytes);
        decoder.accept(bytes);
        io.clear(); // partial bytes have been handed off to the decoder
    }
}
```

This is a **code snippet**; it requires importing `java.nio.ByteBuffer`, `java.nio.channels.SocketChannel`, `java.io.IOException`, and the decoder class from section 7. Do not spin continuously on `n == 0` in non-blocking mode; this snippet fits blocking calls and serves to explain ownership. When using a real selector, only read when readiness is signaled and return control to the event loop when no data is available.

## 12. ByteBuffer Lifecycle and Bugs That Cause Data Loss

### Bug A: Calling `clear()` Before a Frame Is Complete

```java
int n = channel.read(buffer);
if (n > 0) {
    buffer.flip();
    parseWhateverIsAvailable(buffer);
    buffer.clear(); // WRONG if the parser still has unprocessed bytes
}
```

If the parser consumes one frame and leaves the header of the next frame, `clear()` causes the next `read` to overwrite starting at index 0. You need `compact()`, or to copy the leftover bytes into a separate accumulator before `clear()`.

### Bug B: Reading the Header Without Recovering When Payload Is Missing

If the parser calls `getInt()`, finds the payload incomplete, and neither calls `reset()` nor saves the length state, `compact()` leaves only the partial payload, causing the next pass to interpret it as a new header. You must **mark/reset** or use a parser state machine that stores `expectedLength` separately.

### Bug C: Parsing Only One Frame Per Read

`if (buffer.remaining() >= frameSize) parseOne()` is insufficient when the buffer holds multiple frames. Loop until no complete frame remains. Never assume another read event will arrive to process bytes already stored in the buffer.

### Bug D: Calling `flip()` Twice or `compact()` in the Wrong Mode

Calling `flip()` twice in a row when position is 0 can set limit to 0, making the data region look "empty" to the parser. Calling `compact()` on a buffer not in read mode can also retain/shift the wrong region. Keep a consistent convention:

```text
write mode:   channel.read(buffer) or buffer.put(...)
read mode:    buffer.flip() -> parse
write mode:   buffer.compact() (retains partial bytes)
repeat
```

### Bug E: Sharing a Mutable ByteBuffer Across Callbacks/Threads

`ByteBuffer` has mutable position/limit and mutable backing data; it is **not safe for concurrent modification by multiple threads**. If a worker processes a `slice`/`duplicate` pointing to the same data while the event loop compacts/reads more, the worker can observe its payload being overwritten. Copy into an owned buffer, use strict reference counting, or guarantee the memory is not reused before the consumer finishes.

### Bug F: Creating a New Buffer in Every Callback

Allocating `ByteBuffer.allocate(4096)` and discarding it after each `OP_READ` event leaves partial frames nowhere to live between events. Attach state to the connection or protocol session and only release it when the connection closes or the decoder is intentionally reset.

### Bug G: Using `capacity()` as the Valid Byte Count

In read mode, valid data spans from `position` to `limit`. `capacity` is only the total size; it is neither the frame length nor the number of bytes just received. Use `remaining()` and the protocol-validated length.

## 13. Two State-Retention Strategies: Whole-Frame Accumulation vs. State Machine

### 13.1. Cumulative Buffer + mark/reset

Suited for small/medium frames with known bounds:
- Keep both the header and partial payload in the same `ByteBuffer`.
- On each parse pass, attempt to read the length; if incomplete, reset to the start of the frame.
- After processing multiple frames, compact the remaining bytes.
- Requires enough capacity for the largest frame or a bounded growth mechanism.

Pros: concise code, easy to verify. Cons: may copy partial bytes multiple times during compact/grow; peak memory is typically max frame size times connection count.

### 13.2. Incremental State Machine

Can be designed as:

```text
READ_HEADER (needs 4 bytes)
   │ header complete, validate length <= MAX
   ▼
READ_BODY (needs exact length bytes)
   │ body complete
   ▼
DISPATCH_FRAME
   │
   └── return to READ_HEADER for the next frame
```

State consists of `headerBuffer`, `expectedLength`, `bodyBuffer`, `bytesReceived`. A `read` may supply only 2 header bytes, or 10 body bytes; once enough arrive, transition states. More verbose, but well suited for streaming parsers, minimizing copies and controlling memory. Do **not** treat one read as strictly one state transition: a single read can fill the header, the body, and several subsequent frames.

### Comparison

| Criterion | Cumulative buffer | Incremental state machine |
| --- | --- | --- |
| Ease of implementation | High for simple length-prefix | Requires multiple states |
| Partial header/payload | Uses `mark/reset` and `compact` | Stores state/expected byte count |
| Multiple frames in one buffer | `while` loop parses consecutively | State transition loop |
| Large payloads | Needs buffer growth or large capacity | Can fill a dedicated payload buffer |
| Copy optimization | `compact` may shift bytes | Can reduce copies at higher complexity |
| EOF check | `pending.hasRemaining()` | Check state and remaining expected bytes |

Both share the same invariant: **bytes already received that have not yet completed a frame must be preserved accurately**.

## 14. UTF-8, Byte Order, and Protocol Framing

### 14.1. Length-Prefix Must Measure Bytes

If a sender sends `"Xin chào"` in UTF-8, `String.length()` returns the number of UTF-16 code units, **not** the number of bytes on the wire. The sender must encode first:

```java
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
out.writeInt(bytes.length);
out.write(bytes);
```

The receiver reads all those bytes before decoding. If you decode each received chunk as a standalone string, a multi-byte UTF-8 code point can be split across two reads and turn into replacement characters. For a true streaming text parser, use `CharsetDecoder` and preserve decode state across chunks, rather than decoding with `new String(chunk)` independently and concatenating without guaranteeing character boundaries.

### 14.2. Endianness Must Be Consistent

A new `ByteBuffer` defaults to `BIG_ENDIAN`. `DataOutputStream.writeInt` also writes 4 bytes in **big-endian** order. If the sender is designed as little-endian while the receiver calls default `getInt()`, the frame length will be wrong. Document the wire format explicitly:

```text
4 byte big-endian signed int, valid range 0..MAX_PAYLOAD
then exactly length bytes of UTF-8
repeat until EOF
```

If the protocol requires little-endian, set `buffer.order(ByteOrder.LITTLE_ENDIAN)` before parsing and ensure the encoder uses the same convention. Across multiple languages, never rely on the CPU's default byte order.

### 14.3. Not Every Protocol Uses Length-Prefix

Other framing approaches:
- **Delimiter:** a line ending with `\n`. Must retain bytes after the delimiter and retain incomplete lines across reads, enforcing max line length and escaping rules.
- **Fixed-size record:** wait for N bytes; easy to compute, though may require padding.
- **Varint length:** variable-length header; the header **can also be split** across multiple reads, requiring a varint reader state machine and overflow checks.
- **HTTP, WebSocket, TLS/application protocols:** have their own framing/records; do not apply the 4-byte length-prefix example if the protocol does not specify it.

Never use "waiting for a quiet period" or "one `read` equals one message" as framing; network timing is not a protocol boundary.

## 15. EOF, Timeouts, and Error Recovery

Cases to distinguish:

| Case | State | Conclusion |
| --- | --- | --- |
| Complete frames received, then EOF, nothing pending | Complete | Can close the connection cleanly at the framing level |
| EOF after only 2/4 header bytes | Partial header | Truncated protocol frame; report error |
| EOF after length=100 with only 70 bytes received | Partial payload | Truncated protocol frame; do not dispatch the 70 bytes as a complete message |
| `read` returns `0` in non-blocking | No new bytes at that moment | Retain state, wait for next event |
| Full frame read, but handler has not finished | Parser complete, business logic pending | Ensure ownership/queue/backpressure; do not re-read the frame |
| Peer sends negative length or exceeds MAX | Invalid header | Reject, usually close the connection |
| Timeout mid-frame | Cannot assume peer stopped sending | Apply timeout/quota; terminate connection or protocol-specific retry |

The fact that TCP preserves byte order while the connection is active does **not** mean every business request is executed exactly once. If a client sends a request and does not know whether the server processed it before the connection dropped, retries require protocol-level request IDs/idempotency; `compact()` does not solve this.

Do not keep parsing remaining bytes by skipping a bad header and searching for the "next frame" if the protocol has no resynchronization mechanism. With a length-prefix that lacks magic markers/checksums, losing synchronization can cause all subsequent data to be misinterpreted.

## 16. Memory, Ownership, and Backpressure in Multi-Connection Servers

With `N` concurrent connections, if each connection holds a buffer up to `M` bytes, raw buffer cost can be roughly `N × M`, excluding object overhead, TLS, and work queues. For example, a 1 MiB max buffer across 10,000 connections is a huge amount of memory; do not pick max frame sizes arbitrarily.

Practical requirements:
- **Bound frame length** by protocol and reject before allocation, including integer overflow checks.
- **Bound pending bytes and lifetime** of incomplete frames. A peer sending 1 byte per minute can tie up a connection and memory for too long (slowloris-like behavior).
- **Bound frames and bytes processed per event-loop turn** so one connection cannot monopolize CPU time.
- **Backpressure:** when the handler/queue cannot keep up, throttle further reads or adjust `OP_READ`; prevent unbounded queue growth even when the parser is always correct.
- **Ownership:** handlers receive a copied payload or a memory region with managed lifetime, never referencing a buffer that will be overwritten by `compact` or `read`.
- **Non-leaking logs:** log bounded byte counts/connection IDs/error codes; do not dump sensitive payloads into logs.
- **Read/write deadlines:** with non-blocking, use deadlines/selector scheduling; with blocking, configure socket timeouts where appropriate.

`ByteBuffer.allocateDirect` can help under heavy I/O load, but direct buffers have higher allocation/deallocation cost and typically reside off-heap. Choose them only based on real benchmarks/lifetimes. `compact()` and `flip()` follow the same logic for both heap and direct buffers; never assume a direct buffer always exposes an accessible backing array via `array()`. The lesson examples use heap buffers for easy verification.

A common pitfall: if the parser hands `ByteBuffer.slice()` to a worker, the slice still **shares the backing data**. `slice()` does not copy the payload by default. Copy it or preserve ownership before reusing the memory for the next read.

## 17. Testing the Parser: Splitting Anywhere, Coalescing Multiple Frames, and EOF

A good test should start from **canonical wire bytes** and vary how chunks are split independently of the message content. For the same sequence of wire bytes, the decoder must emit the exact same list of frames regardless of where the splits fall.

| Test | Input data | Expected result |
| --- | --- | --- |
| 4-byte header across 4 reads | `[00] [00] [00] [03] [CAT]` | Do not dispatch while header is incomplete |
| Complete header, missing payload | `[len=5][HE]` then `[LLO]` | Dispatch `HELLO` only when all 5 bytes arrive |
| Two frames in one chunk | `[len=1][A][len=2][OK]` | Dispatch two frames consecutively |
| One frame ends mid-chunk | `[frame A][2 bytes of header B]` | Dispatch A, retain 2 bytes of header B |
| Initial buffer too small | Valid frame longer than current capacity | Grow boundedly or use separate payload state, do not spin |
| Negative length / exceeds max | `[FF FF FF FF]` or length > MAX | Reject before allocation |
| EOF mid-header | Only 1–3 header bytes then EOF | Report truncated frame |
| EOF mid-body | Length=6, only 3 body bytes then EOF | Report truncated frame |
| EOF after complete frame | Nothing pending | Clean termination |
| Empty frame | Length=0 | Dispatch empty frame or reject per policy; do not confuse with EOF |
| UTF-8 split across two reads | Multi-byte code point cut in half | Decode correctly once full payload arrives |
| One slow connection, one fast connection | Two separate channels/states | Do not mix data or cause the fast connection to lose state |

In unit tests, you can build a canonical `byte[] wire`, loop over every cut position `i` from 0..wire.length, feed `wire[0:i]` and `wire[i:end]`, and compare the emitted frame list against expected results. With multiple frames, test arbitrary random partitions while **preserving byte order**. Relying solely on timing/loopback tests is insufficient because the OS may incidentally coalesce all data into a single read and mask bugs.

At the integration level, test lifecycle cases separately: close mid-frame, timeouts, multiple connections, full buffers, overloaded downstream queues, malicious payloads, and buffer ownership handoffs.

## 18. Practical Workflow for Processing a Single Read

When receiving a read event from `SocketChannel`, you can follow this sequence:

1. Retrieve the **connection state** holding the accumulator/parser and limit counters.
2. Read into the buffer in **write mode** with `remaining() > 0`; if no space remains, process frames or grow boundedly **before reading**.
3. If `n > 0`, switch to **read mode** with `flip()`; parse all complete frames.
4. For an incomplete header, do not call `getInt`; for an incomplete payload, **restore position to the start of the frame** or save separate state.
5. Dispatch complete payloads, managing ownership so the original buffer can be safely reused.
6. Call `compact()`, retaining unprocessed bytes; the next read appends after those bytes.
7. If `n == 0` in non-blocking mode, stop the read loop as appropriate and wait on the selector; if `n == -1`, check pending state/EOF and clean up.
8. Enforce limits on pending bytes, max payload, timeouts, processing rate, and queues to prevent resource exhaustion.

**Correctness criterion:** For the same byte stream, the parser outputs the same complete messages **regardless of how many reads it is split across**, and never emits an incomplete message.

## 19. Self-Check Questions

**Question 1.** After `flip()`, a ByteBuffer has `position=6` and `limit=9`. The parser has finished reading up to index 5, leaving 3 bytes belonging to the next frame. If `compact()` is called, what is the new state?  
**Answer:** Retains the 3 bytes `[6,9)` shifted to the front, `position=3` and `limit=capacity` (write mode).

**Question 2.** Why does `clear()` easily lose messages when the parser only has the first 2 bytes of a header?  
**Answer:** `clear()` resets position to 0 so the next write overwrites the partial header; you need `compact()` or to copy to another accumulator.

**Question 3.** A buffer has header length=5 and only 2 payload bytes. The parser already called `getInt()`. If it does not call `reset()` before `compact()`, what bug occurs?  
**Answer:** The 4-byte header is treated as consumed, leaving the 2 payload bytes at the start of the buffer; the next parse pass misinterprets the protocol. You must retain both header+partial payload or transition to a PAYLOAD state with the saved length.

**Question 4.** If a single read delivers three complete frames, where can a parser using `if` to read only the first frame break?  
**Answer:** The remaining two frames are already inside the application but may never be processed if no subsequent callback arrives; you must loop until only an incomplete frame remains.

**Question 5.** Does `read() == 0` in a non-blocking SocketChannel mean EOF?  
**Answer:** No. EOF returns `-1`; `0` means no bytes were added to the buffer at that time, or there was no space to receive. Do not clear pending state.

**Question 6.** Why shouldn't `String.length()` be used as a UTF-8 length-prefix?  
**Answer:** It counts UTF-16 code units, not UTF-8 bytes on the wire. You must encode first and use `bytes.length`.

**Question 7.** A frame is 100 bytes long, and the buffer capacity is 32 bytes. What must the parser do?  
**Answer:** If length <= the allowed limit, grow boundedly or save state and collect the payload into a separate buffer; never spin reading into a full buffer or silently truncate.

**Question 8.** Why can handing `ByteBuffer.slice()` to a worker and immediately calling `compact()`/writing again cause bugs?  
**Answer:** A slice shares memory with the original buffer; the worker may read overwritten data. You need a copy or safe ownership/lifetime management.

**Question 9.** If EOF arrives after two complete frames have been dispatched and 1 byte of the third frame's header remains, can you report a clean termination?  
**Answer:** No. 1 partial header byte remains, so you must report a truncated frame and handle the connection according to the protocol.

**Question 10.** Why is testing a parser by feeding it one byte at a time an important test?  
**Answer:** It proves the parser does not depend on chunk size and preserves state when headers/payloads are fragmented. You must also test multiple frames in a single chunk to prove it handles coalescing.

## 20. References

- Java SE 17 `ByteBuffer` — `flip()`, `compact()`, `mark()`, `reset()`, byte order, and direct buffers: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 `Buffer` — position, limit, capacity, remaining rules: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html
- Java SE 17 `SocketChannel` — `read` may return any byte count up to the limit, `0`, or `-1`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html
- Java SE 17 `SelectionKey` — `OP_READ`, per-connection attachment: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html
- Java SE 17 `DataOutputStream` — 4-byte big-endian `writeInt`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html
- RFC 9293, Transmission Control Protocol — byte stream and segment boundaries do not map directly to the application: https://www.rfc-editor.org/rfc/rfc9293
