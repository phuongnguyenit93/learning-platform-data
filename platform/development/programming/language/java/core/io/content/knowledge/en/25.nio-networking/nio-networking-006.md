# Partial Read, Partial Write, and Preserving State Across Readiness Events in Java NIO

A TCP connection transmits a continuous **byte stream**. A single `SocketChannel.read(ByteBuffer)` call does not correspond to exactly one business message; nor does a single `write(ByteBuffer)` call guarantee the entire message has been sent. Especially with `SocketChannel` in non-blocking mode and `Selector`, `read()` or `write()` can process **only part of the data**, or return `0` without being an error.

The key problem is: **after each readiness event, you must preserve the bytes already received, the bytes still left to send, and the message parsing state so the next readiness event resumes from the exact right place**. Discarding buffers between `select()` calls can lose bytes, send incomplete messages, misassemble frames, or spin the CPU when the socket cannot make progress.

## 1. A TCP Stream Has No Message Boundaries

Suppose a client sends the 6-byte UTF-8 string `HELLO\n`. On the server side, valid reads might look like:

```text
Client write:  [ H E L L O \n ]

Server read #1: [ H E ]
Server read #2: [ L ]
Server read #3: [ L O \n ]
```

Or the server might read all 6 bytes in one shot. Conversely, if the client sends two messages `HELLO\n` and `WORLD\n`, the server might receive bytes from both in a single read.

Causes include TCP buffer states, network conditions, `ByteBuffer` size, processing speed, and OS scheduling. Therefore, **each socket readable notification does not represent one complete message**.

The application must define **framing**, such as:

- Delimiter termination (`\n` for text lines).
- Length prefix: four leading bytes representing the payload byte count, followed by reading that exact number of bytes.
- Fixed-structure frames, if the protocol genuinely defines a constant size.
- A custom protocol parser capable of receiving multiple frames or one frame split into multiple parts.

Framing must operate over the **continuous byte stream**. With UTF-8, a single character can span multiple reads; never do `new String(chunk)` and assume each chunk is complete text.

## 2. Exact Meaning of `SocketChannel.read` Return Values

For a `SocketChannel` registered for `OP_READ`, the call:

```java
int n = socket.read(inputBuffer);
```

has three distinct kinds of outcomes:

| Value | Meaning | What the application should do |
| --- | --- | --- |
| `n > 0` | `n` bytes were placed into the remaining space of `inputBuffer` | Preserve received data and attempt to parse complete frames |
| `n == 0` | Zero bytes read in this call; normal for non-blocking sockets or a full buffer | Do not treat as EOF, do not spin indefinitely; keep state for future readiness |
| `n == -1` | Remote peer closed the channel's read stream (receive-side EOF) | Decide to close the connection, handle half-close, or check incomplete frames per protocol |

Reading into a buffer advances `inputBuffer.position()` by the exact number of bytes read, **without changing `limit()` itself**. If the buffer already held three unprocessed bytes before the call, the next read must append right after those three bytes.

Illustrative snippet showing the idea:

```java
// socket: non-blocking SocketChannel; input: long-lived ByteBuffer.
int n = socket.read(input);
if (n > 0) {
    input.flip();       // Read the bytes received so far.
    parseFrames(input); // Frame parser may leave trailing partial data.
    input.compact();    // Shift unconsumed bytes to front, ready to read more.
} else if (n == -1) {
    closeOrHalfClose(socket); // Illustrative business handler.
}
```

Both `parseFrames` and `closeOrHalfClose` are **undefined illustrative functions**; this snippet is not a standalone Java program. Most importantly: `parseFrames` must leave `position` right after the last consumed byte; `compact()` preserves the remaining bytes. If an application uses a different stateful parser, it must still preserve unprocessed bytes.

## 3. Partial Write and Remaining `ByteBuffer` State

Non-blocking writes follow similar rules:

```java
int n = socket.write(outputBuffer);
```

- If `n > 0`, the channel accepted `n` bytes from the buffer; `outputBuffer.position()` advances by `n`. Bytes accepted by the kernel into the send path **are not guaranteed to have been received or processed by the remote peer**.
- If `n == 0`, at that moment the channel could not write any more bytes (or the buffer had none remaining). When data remains, retain the buffer and wait for the next writable event.
- `write(ByteBuffer)` has no contract to "write all of `remaining()` in a single call". You must handle partial writes based on the return value and `buffer.hasRemaining()`.

For example, with a buffer holding the 5 bytes `ABCDE`, write calls might proceed as:

```text
Before write: position=0, limit=5, remaining=5
write #1:     returns 2 -> position=2, remaining=3
write #2:     returns 0 -> position=2, remaining=3
write #3:     returns 3 -> position=5, remaining=0
```

When returning from the event loop, **do not call `rewind()` or `flip()` on an output buffer that has not finished sending**, as doing so can resend already-sent bytes or corrupt the valid data range. Keep the buffer at its current `position` until `hasRemaining()` becomes `false`.

If multiple frames are waiting, each connection typically maintains an **outbound buffer queue**. Remove the head item only after that buffer has zero remaining bytes; only then move to the next frame to preserve TCP stream order.

## 4. Why Must State Be Preserved Across `select()` Calls?

`Selector` lets one thread monitor many `SelectableChannel` instances via `SelectionKey` objects. With non-blocking sockets:

1. Register `OP_READ` when wanting to receive data.
2. When `select()` reports `isReadable()` on a key, attempt to read and update the input buffer.
3. Once a message is complete, prepare the response as an output buffer and register `OP_WRITE` if bytes remain to be sent.
4. When a key reports `isWritable()`, attempt to write the remainder; if incomplete, keep `OP_WRITE`.
5. Once the output buffer has no remaining bytes, **clear `OP_WRITE`** to avoid continuous selection wakeups since sockets are usually writable even with nothing left to send.

Readiness is a **hint of operational capability**, not a guarantee that read/write will process all desired data or always make progress. Even when a selected key reports ready, `read` or `write` can still return `0`; state must be updated based on the actual return value.

### A per-connection state structure

A common pattern is a `Session` or `ConnectionState` attached to the `SelectionKey`:

```java
// Illustrative definition.
final class ConnectionState {
    final ByteBuffer inbound = ByteBuffer.allocate(8192);
    final java.util.ArrayDeque<ByteBuffer> outgoing =
            new java.util.ArrayDeque<>();
    boolean peerInputClosed;
}
```

After `channel.register(selector, SelectionKey.OP_READ, state)`, you can retrieve the state via `(ConnectionState) key.attachment()`. **Do not recreate `ByteBuffer` on every selector iteration**: a fresh buffer loses partial frame bytes from the previous turn.

State may also need to hold expected payload byte counts, parser state, charset decoders, deadlines, limit counters, half-close flags, and in-flight request/response protocols.

## 5. `flip()`, `compact()`, and Partially Received Data

Suppose an application expects a frame ending with `\n`, yet the first read receives only `HEL`:

```text
Buffer after read #1:
[ H E L _ _ _ _ _ ]  position=3, limit=8
flip():
[ H E L _ _ _ _ _ ]  position=0, limit=3
parser: no '\n' yet, consumes 0 bytes
compact():
[ H E L _ _ _ _ _ ]  position=3, limit=8

read #2 appends "LO\n":
[ H E L L O \n _ _ ] position=6, limit=8
flip() -> parser receives full "HELLO\n".
compact() -> position=0, limit=8 if all bytes consumed.
```

If the buffer contains `ONE\nTWO`, the parser should extract frame `ONE\n`, retain `TWO` via `compact()`, and wait for the missing `\n`. If the buffer contains `ONE\nTWO\n`, the parser must be able to emit **two frames during the same parse pass**.

Distinguish clearly:

- `flip()`: switches from writing data into the buffer to reading the written data out.
- `clear()`: sets position=0, limit=capacity, **does not preserve unprocessed bytes** and does not physically erase bytes.
- `compact()`: keeps remaining bytes in `position..limit`, shifts them to the beginning of the buffer, and resets state to continue receiving.

If the parser consumed every byte, `compact()` results in position=0, matching a fresh write-ready state. If part of a frame remains, `compact()` protects it.

### When the input buffer is full without a complete frame

If `inbound.remaining()==0` in write mode yet the parser still has not completed a frame, the application cannot read additional bytes into the existing buffer. You need a clear policy: cap frame size, grow the buffer up to an allowed limit, or reject oversized messages. Never repeatedly call `read()` into a full buffer and spin on `0`.

## 6. Complete Java 17+ Program: One TCP Connection, Multiple Readiness Turns

The following example uses TCP loopback so it can run standalone. The client sends an ASCII frame `PING\n`, and the server handles it with a non-blocking `SocketChannel` and `Selector`. To **guarantee demonstrating** state preservation, each readable callback is capped to reading at most **2 bytes**, and each writable callback is capped to writing at most **2 bytes**, by temporarily lowering `ByteBuffer.limit()`. This cap is artificially imposed by the example to force multiple steps; in real applications reads/writes can be short due to network or OS conditions.

Create file **`PartialIoSelectorDemo.java`**:

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public final class PartialIoSelectorDemo {
    private static final byte[] REQUEST =
            "PING\n".getBytes(StandardCharsets.US_ASCII);
    private static final byte[] RESPONSE =
            "ACK:PING\n".getBytes(StandardCharsets.US_ASCII);

    private PartialIoSelectorDemo() {}

    private static final class Session {
        final ByteBuffer inbound = ByteBuffer.allocate(32);
        ByteBuffer outbound;
        int readFragments;
        int writeFragments;
        boolean done;
    }

    public static void main(String[] args) throws IOException {
        try (ServerSocketChannel listener = ServerSocketChannel.open();
             SocketChannel client = SocketChannel.open();
             Selector selector = Selector.open()) {

            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            client.connect(listener.getLocalAddress());

            try (SocketChannel accepted = listener.accept()) {
                accepted.configureBlocking(false);
                Session session = new Session();
                accepted.register(selector, SelectionKey.OP_READ, session);

                // Client uses blocking mode to send a small request.
                writeAll(client, ByteBuffer.wrap(REQUEST));

                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(5);

                while (!session.done) {
                    if (System.nanoTime() >= deadline) {
                        throw new IOException("Timed out waiting for I/O");
                    }

                    if (selector.select(100) == 0) {
                        continue;
                    }

                    Iterator<SelectionKey> it =
                            selector.selectedKeys().iterator();
                    while (it.hasNext()) {
                        SelectionKey key = it.next();
                        it.remove();
                        if (!key.isValid()) {
                            continue;
                        }

                        Session state = (Session) key.attachment();
                        if (key.isReadable()) {
                            readOneFragment(key, state);
                        }
                        if (key.isValid() && key.isWritable()) {
                            writeOneFragment(key, state);
                        }
                    }
                }

                ByteBuffer reply = ByteBuffer.allocate(RESPONSE.length);
                while (reply.hasRemaining()) {
                    int n = client.read(reply);
                    if (n < 0) {
                        throw new EOFException("Reply truncated");
                    }
                    if (n == 0) {
                        throw new IOException("No client read progress");
                    }
                }
                reply.flip();

                System.out.println("request=PING");
                System.out.println("reply="
                        + StandardCharsets.US_ASCII.decode(reply)
                                .toString().strip());
                System.out.println("read fragments >=3: "
                        + (session.readFragments >= 3));
                System.out.println("write fragments >=5: "
                        + (session.writeFragments >= 5));
            }
        }
    }

    private static void readOneFragment(SelectionKey key, Session state)
            throws IOException {
        SocketChannel socket = (SocketChannel) key.channel();

        if (!state.inbound.hasRemaining()) {
            throw new IOException("Request exceeds input capacity");
        }

        int oldLimit = state.inbound.limit();
        int cap = Math.min(2, state.inbound.remaining());
        state.inbound.limit(state.inbound.position() + cap);

        int n;
        try {
            n = socket.read(state.inbound);
        } finally {
            state.inbound.limit(oldLimit);
        }

        if (n < 0) {
            throw new EOFException("Peer closed before request completed");
        }
        if (n == 0) {
            return; // Wait for next readability, preserving position.
        }

        state.readFragments++;
        int written = state.inbound.position();
        if (state.inbound.get(written - 1) != (byte) '\n') {
            return; // Incomplete frame; keep received bytes in inbound.
        }

        state.inbound.flip();
        byte[] frame = new byte[state.inbound.remaining()];
        state.inbound.get(frame);
        if (!Arrays.equals(frame, REQUEST)) {
            throw new IOException("Unexpected request");
        }

        state.outbound = ByteBuffer.wrap(RESPONSE);
        key.interestOps(SelectionKey.OP_WRITE);
    }

    private static void writeOneFragment(SelectionKey key, Session state)
            throws IOException {
        SocketChannel socket = (SocketChannel) key.channel();
        ByteBuffer out = state.outbound;
        if (out == null) {
            throw new IOException("No outbound frame");
        }

        int oldLimit = out.limit();
        int cap = Math.min(2, out.remaining());
        out.limit(out.position() + cap);

        int n;
        try {
            n = socket.write(out);
        } finally {
            out.limit(oldLimit);
        }

        if (n > 0) {
            state.writeFragments++;
        }
        if (!out.hasRemaining()) {
            key.interestOps(0); // Do not stay registered for OP_WRITE when no data remains.
            state.done = true;
        }
        // If n==0 or bytes remain: preserve out.position().
    }

    private static void writeAll(SocketChannel channel, ByteBuffer data)
            throws IOException {
        while (data.hasRemaining()) {
            int n = channel.write(data);
            if (n == 0) {
                throw new IOException("No blocking write progress");
            }
        }
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac PartialIoSelectorDemo.java
java PartialIoSelectorDemo
```

Output when TCP loopback and selector behave normally:

```text
request=PING
reply=ACK:PING
read fragments >=3: true
write fragments >=5: true
```

The final lines **do not assume exact read/write counts**. Because the program caps each read/write to at most 2 bytes, the 5-byte frame needs at least 3 successful read turns and the 9-byte frame needs at least 5 successful write turns. The OS may cause even more turns; `>=3` and `>=5` still evaluate to `true`. The 5-second timeout merely protects the demo from hanging forever in abnormal network environments.

### Where is state stored?

- `Session.inbound` **is not reallocated between readiness turns**. After the first read turn, position may be 2; the next turn continues from there until the newline byte arrives.
- `Session.outbound` is created once when the request frame is complete. After each writable turn, `outbound.position()` advances by the exact number of bytes written.
- `Session.readFragments`, `writeFragments`, and `done` are stored in `Session`, attached to `SelectionKey` via `register(..., session)` and `attachment()`.
- Once the request is received, the server switches interest from `OP_READ` to `OP_WRITE`. Once sending finishes, it clears interest and exits the demo.
- Both temporary `limit()` reductions are restored inside `finally`, preserving the buffer's original capacity and limit.
- The demo intentionally accepts only **one specific ASCII frame** and does not support pipelining multiple requests; that is a demo-protocol limitation. Real servers must parse multiple frames in one buffer, preserve partial frames with `compact()` or a stateful parser, and handle EOF/half-close.

The program does not require running an external server; both connection endpoints are created inside a single process over loopback. With non-blocking sockets, `select()` reporting ready must never be mistaken for a complete frame. The example proves pending bytes survive across multiple readiness turns.

## 7. Designing a Length-Prefix Message Parser

A newline-based protocol is convenient for illustration, though unsuitable for arbitrary binary payloads. For a frame consisting of **4 length bytes** (big-endian) followed by `length` payload bytes, the parser needs two phases:

1. `READ_LENGTH`: read all 4 bytes; if only 1–3 bytes have arrived, keep them and do not decode the length yet.
2. `READ_PAYLOAD`: once length is decoded and validated against limits, continue collecting the full payload; upon completion transition back to `READ_LENGTH` for the next frame.

Two separate buffers can be used:

```java
// State machine sketch; variables stored per connection.
ByteBuffer lengthBytes = ByteBuffer.allocate(4);
ByteBuffer payload = null;

// In READ_LENGTH: fill lengthBytes until !hasRemaining().
if (!lengthBytes.hasRemaining()) {
    lengthBytes.flip();
    int length = lengthBytes.getInt(); // BIG_ENDIAN by default.
    if (length < 0 || length > MAX_FRAME_BYTES) {
        throw new IOException("Invalid frame length");
    }
    payload = ByteBuffer.allocate(length);
    lengthBytes.clear();
    // Transition state to READ_PAYLOAD.
}
```

This is a **sketch**, omitting `MAX_FRAME_BYTES`, state definitions, byte accumulation, and payload handling; it is not a standalone compilable program. Ensure bytes are never lost when a single `read` finishes the header and also contains part of the payload. Never allocate a buffer from length before validating limits, and also bound total memory in use across multiple connections.

If a frame has length 0, protocol policy must decide whether that is a valid empty frame or an error; if valid, the parser must complete immediately without waiting to `read` more bytes into a buffer with remaining=0.

## 8. Managing `OP_WRITE` and Backpressure

A common mistake is registering right upon connection creation:

```java
channel.register(selector, SelectionKey.OP_READ | SelectionKey.OP_WRITE);
```

When no outbound data is waiting, most sockets remain writable most of the time and the selector can return readiness continuously. The event loop wakes up pointlessly and drives CPU usage high.

Common policy:

- **No outbound data waiting:** register interest only in `OP_READ` (plus other needed bits if required by the protocol).
- **Outbound data remaining:** add `OP_WRITE` to get another chance once the socket accepts more bytes.
- **Outbound queue is empty:** remove `OP_WRITE` immediately.
- **Outbound queue exceeds threshold:** apply backpressure: temporarily pause/remove `OP_READ` for that connection, reject new requests, cap memory, or close the connection per service policy.

Updating interest bits must **preserve other required bits**. For instance, when already interested in reads:

```java
// Sketch: key is valid and operation is performed by the event-loop owner.
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
// When the queue is empty:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

If another thread adds data to the outbound queue, coordinate the `interestOps` update and consider calling `selector.wakeup()` so the event-loop thread does not wait out its timeout before processing. Never let multiple threads concurrently mutate `ByteBuffer.position`, queues, and keys without consistent ownership or synchronization.

### When one connection is very busy

A single read/write callback should not drain a socket indefinitely, or other connections may suffer starvation. Enforce a per-turn work budget—such as a maximum number of bytes, frames, or time—before yielding to service other keys. The 2-byte cap in the demo was chosen to observe partial I/O; in real systems choose thresholds based on benchmarks and latency/throughput goals.

## 9. EOF, Half-Close, Timeouts, and Resource Cleanup

`read() == -1` indicates the remote peer closed its sending direction (or the socket reached read-side EOF). In TCP, **half-close** can occur: the peer called `shutdownOutput()` yet can still receive data in the reverse direction. Applications should not blindly discard the outbound queue in every protocol; policy depends on the received request, pending response, and connection termination semantics.

When EOF arrives mid-frame:

- If the protocol requires complete frames, report an incomplete-frame error.
- If the protocol uses EOF itself as the message terminator, handle it by that convention and avoid mixing it with length-prefix/newline framing.
- If outbound data remains to be sent, you may keep the connection open until flushed or until a deadline expires, if protocol and socket state permit.

When closing a selector-registered channel, its selection key is cancelled; remove the key from tracking structures and release references to state/buffers. On I/O errors, timeouts, or protocol violations, close cleanly rather than holding queued buffers forever.

Complete connection state normally requires read timeouts, write timeouts, maximum frame sizes, maximum pending bytes, and idle timeouts. Readiness alone enforces none of these limits.

## 10. Logging State to Debug Partial I/O

When diagnosing issues, log **actual bytes processed** rather than assumptions about a single readiness notification:

| Field | Purpose |
| --- | --- |
| `readResult` | Actual bytes read, 0, or -1 |
| `input.position/limit/capacity` | Bytes received and remaining space |
| `parserState` | Waiting for header, payload, delimiter, or processing request |
| `writeResult` | Bytes actually accepted by the channel |
| `output.remaining` | Remaining bytes left to send in the current buffer |
| `pendingQueueBytes` | Outbound memory pressure on the connection |
| `key.interestOps/readyOps` | What is registered vs what the selector just reported |
| Last receive/send timestamp | For timeouts and progress monitoring |

Do not log full payloads if they contain secrets or personal data; focus on metadata, byte counts, and appropriate connection identifiers.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating every `read()` as a complete message | Broken frame splits or merged frames | Use framing and a stateful parser |
| Treating `0` as EOF | Prematurely closing valid connections | Only `-1` indicates EOF on `read` |
| Reading a few bytes then allocating a new input buffer on next readiness | Lost partial header/payload | Keep the buffer in connection state |
| Calling `flip/rewind` after an incomplete `write` | Duplicate bytes or corrupted boundaries | Keep `position` until `hasRemaining()==false` |
| Calling `clear()` while parser still has unconsumed bytes | Partial frame data discarded | Use `compact()` or separate parser state |
| Leaving `OP_WRITE` registered with an empty queue | `select()` wakes continuously, high CPU | Register write interest only with pending output |
| Looping when `read/write` returns 0 | Busy-loop starving other connections | Wait for next readiness via selector |
| Processing one key indefinitely or leaving outbound queue unbounded | Starvation, growing memory/latency | Per-turn byte budget and backpressure |
| Decoding UTF-8 chunk by chunk independently | Corrupted split multi-byte characters | Decode full frame bytes or use stateful `CharsetDecoder` |
| Ignoring partial frame check when `read()==-1` | Accepting truncated messages | Define EOF and incomplete-frame rules |
| Updating `interestOps` from another thread without wakeup/coordination | Delayed or missed progress until next wakeup | Single event-loop owner, safe queue, and `selector.wakeup()` |

**Remember:** In non-blocking Java NIO, each `OP_READ` or `OP_WRITE` readiness notification is only an *opportunity* to process data. **Always rely on actual bytes read/written, retain buffers and parser state across `select()` calls, register `OP_WRITE` when outbound data remains, and remove it once finished**. That is the foundation for a selector-based server to handle TCP streams accurately and efficiently.
