# Storing Per-Connection Protocol State and Buffers with Selector

## 1. The Problem: One Selector Handling Multiple Connections, Each at Different Progress

Java NIO allows a single thread to use a `Selector` to monitor multiple `SocketChannel` instances. This approach avoids dedicating a thread blocked in `read()` for each connection, but it also introduces a mandatory requirement: **protocol state and unprocessed data must belong to the right connection**.

Suppose two clients, A and B, both use a TCP protocol where each message has a 4-byte header representing the payload length:

```text
Client A sends frame "ALPHA":
  [00 00 00 05][41 4C 50 48 41]
Client B sends frame "BETA":
  [00 00 00 04][42 45 54 41]

One Selector processing pass might see:
  event #1: A received the first 2 bytes of the header
  event #2: B received the first 1 byte of the header
  event #3: A receives the rest of the header + 2 payload bytes
  event #4: B receives enough data and completes "BETA"
  event #5: A receives enough data and completes "ALPHA"

Correct result: BETA completes before ALPHA.
A's header must not be combined with B's payload.
```

If the program creates **a shared `ByteBuffer`** for all channels and overwrites old bytes with new data, the parser could mistakenly read A's data as B's message. If the program allocates a new buffer on every `OP_READ`, the missing header/payload bytes from the previous read will be lost. Similarly, if a global `expectedLength` variable is stored, reading B's header can overwrite A's pending length.

**Solution:** Each connection has its own `ConnectionState` object attached to that channel's `SelectionKey` (or stored in a consistently managed `SocketChannel → ConnectionState` map). The state persists **across multiple readiness/read/write events** and is released when the connection ends.

After this lesson, you should be able to:
- Correctly explain the `Selector` → `SelectionKey` → `SocketChannel` → `ConnectionState` relationship.
- Store **inbound buffer, outbound queue, parser state, handshake flags, timeout, and quota** separately per connection.
- Reassemble and parse TCP frames across multiple `read` calls without losing, duplicating, or mixing bytes between clients.
- Use `SelectionKey.attach()/attachment()` together with `OP_READ`/`OP_WRITE` properly.
- Clean up state on EOF, error, key cancellation, or channel close; protect the server against slow clients and memory growth.

## 2. Selector Tracks Readiness, Not the Protocol Itself

`Selector` lets an event loop thread ask the operating system which operation groups the registered channels are ready for. In Java 17, the common interest/ready types are:

| Operation | Primary Target | Meaning |
| --- | --- | --- |
| `SelectionKey.OP_ACCEPT` | `ServerSocketChannel` | An incoming connection can be accepted on the listener |
| `SelectionKey.OP_CONNECT` | `SocketChannel` | Nonblocking connect can complete or report an error; call `finishConnect()` |
| `SelectionKey.OP_READ` | `SocketChannel` | Data can be read, EOF reached, or an error occurred; **does not promise a full message** |
| `SelectionKey.OP_WRITE` | `SocketChannel` | At least a partial write is possible, but does not promise draining the entire queue |

`key.isReadable()` is a **readiness signal**, not an answer to "is there a complete frame?". The parser must rely on **received bytes + framing rules**. `SocketChannel.read(ByteBuffer)` in nonblocking mode may return `0`, a positive byte count smaller than expected, or `-1` if EOF has been reached.

`SelectionKey` represents **a registration of a channel with a Selector**. It has:
- `channel()`: the channel being monitored.
- `selector()`: the selector managing the registration.
- `interestOps()`: operations you **want to monitor**.
- `readyOps()` and `isReadable()`/`isWritable()`: operations **reported as ready** in that select pass.
- `attachment()`: **an arbitrary application object** attached to the key.
- `isValid()` and `cancel()`: check/cancel the registration.

A `SelectionKey` **does not store application buffers** or decode protocols on its own. Those are defined by the program in the attachment.

## 3. Per-Connection State Ownership Model

A clear architecture:

```text
                        ┌────────────────────────────┐
                        │ Selector + event loop      │
                        └──────────────┬─────────────┘
                                       │
               ┌───────────────────────┼────────────────────────┐
               ▼                       ▼                        ▼
        Listener Key             Key A / Socket A        Key B / Socket B
        OP_ACCEPT                OP_READ, OP_WRITE       OP_READ
        attachment: null         attachment: State A     attachment: State B
                                 ┌──────────────────┐    ┌──────────────────┐
                                 │ inbound A        │    │ inbound B        │
                                 │ pending frames A │    │ pending frames B │
                                 │ outbound queue A │    │ outbound queue B │
                                 │ protocol phase A │    │ protocol phase B │
                                 │ quota/deadline A │    │ quota/deadline B │
                                 └──────────────────┘    └──────────────────┘

A's data flows only into State A; B's data flows only into State B.
```

A typical state class may contain:

| Field | Purpose | Ownership Notes |
| --- | --- | --- |
| `ByteBuffer inbound` | Accumulates unparsed TCP bytes | One buffer or dedicated accumulator per connection |
| `Deque<ByteBuffer> outbound` | Responses/bytes waiting to be written to the socket | One queue per channel; preserves `position` on partial write |
| `int expectedPayloadBytes` | Frame length parsed from header when using a state machine | Not global; reset per frame |
| `ProtocolPhase phase` | E.g. awaiting handshake, active, closing | Transitions according to **that connection's** protocol sequence |
| `long lastActivityNanos` | Detects idle/slow connections | Measured using a monotonic clock source |
| `int queuedBytes` | Enforces quota and backpressure | Updated on queue/flush |
| `String requestId` or stream map | Tracks requests or logical streams within a connection | If the protocol multiplexes multiple streams, state also has a sub-layer |

Not every field is required. For a small length-prefix example, one `ByteBuffer inbound` and a processed frame counter suffice. For multi-step protocols (TLS, authentication, WebSocket, RPC), state must also represent handshake steps, fragments, outstanding requests, timeouts, and write queues.

**Boundary rule:** one connection state object belongs to **one connection** and lives until close/cleanup. Do not share one instance across multiple clients just because they use the same protocol.

## 4. Attaching State to SelectionKey

When the listener accepts a client:

```java
SocketChannel accepted = listener.accept();
if (accepted != null) {
    accepted.configureBlocking(false);
    ConnectionState state = new ConnectionState(nextConnectionId++);
    accepted.register(selector, SelectionKey.OP_READ, state);
}
```

This is an **illustrative code snippet**; `listener` is already configured nonblocking, `selector` is the event loop selector, `nextConnectionId` is an ID generator, and `ConnectionState` is an application class. `register(selector, ops, attachment)` creates/configures the registration with the attachment. If a nonblocking server socket has multiple pending connections to accept, you typically loop `accept()` until it returns `null`.

When a read event occurs:

```java
if (key.isValid() && key.isReadable()) {
    SocketChannel channel = (SocketChannel) key.channel();
    ConnectionState state = (ConnectionState) key.attachment();
    int n = channel.read(state.inbound);
    if (n > 0) {
        parseAvailableFrames(state);
    } else if (n == -1) {
        finishOrRejectPendingFrame(state);
        closeConnection(key);
    }
}
```

This is an **illustrative code snippet**; the three handler methods and the state class are application-defined. The key point is **retrieving state from the notified key itself**, rather than relying on a global "current client" variable.

`key.attach(state)` can also be used when registering first and attaching state afterward. Each key has exactly **one attachment slot**; to store multiple fields, wrap them in a single object. Attaching a new object via `attach(other)` replaces the old attachment; therefore, do not accidentally replace a state that holds a partial buffer.

Besides attachments, you can use a `Map<SocketChannel, ConnectionState>`; you need to key by channel identity or an appropriate connection key, manage concurrency, and remove entries on close. Attachments usually require fewer lookups because the callback already has the `SelectionKey`. Do **not** assume attachments are automatically persisted across application restarts or safely shared across multiple threads.

## 5. Event Boundaries Are Not Message Boundaries

With TCP, a single `read` can return:
- The first 2 bytes of a 4-byte header.
- A complete header but only part of the payload.
- One complete frame and the first 3 bytes of the next header.
- Multiple complete frames.
- 0 bytes (especially in nonblocking mode).
- `-1` when EOF is reached.

No scenario allows concluding "one OP_READ = one request". For example, a wire format with a 4-byte big-endian length:

```text
Client A: [00 00]                             (header missing 2 bytes)
Client B: [00]                                (header missing 3 bytes)
Client A: [00 05 41 4C]                       (A header complete, A payload only "AL")
Client B: [00 00 04 42 45 54 41]              (B has complete "BETA")
Client A: [50 48 41]                          (A has complete "ALPHA")
```

While A is still pending, the event loop may process hundreds of events from B or other clients. Therefore:
- A's **pending header** must be kept in A.
- A's **expected length** must be kept in A.
- A's **pending payload** must be kept in A.
- A's **queued response bytes** must be kept in A.

You cannot simply create a `ByteBuffer` at the start of a callback and discard it at the end if the protocol allows split frames. A new buffer can be used as a shared I/O scratch buffer if **before reuse** all unprocessed bytes are transferred and preserved accurately in the connection's own state; however, this pattern requires clear ownership and exact-size copying.

## 6. ByteBuffer: flip, compact, and Unprocessed Bytes

A `ByteBuffer` used as an accumulator typically stays in **write mode** outside the parser:

```text
Before read:
[pending bytes][free space to write more]
position = number of pending bytes; limit = capacity

SocketChannel.read(buffer):
[pending bytes][newly received bytes][free space]
position advances by number of new bytes

flip():
[bytes available to parse in read mode][region beyond limit]
position = 0; limit = total pending + new bytes

Parser consumes all complete frames:
[processed bytes][partial header/payload]
                 ▲ position

compact():
[partial header/payload][free space to read more]
position = number of remaining partial bytes; limit = capacity
```

The methods:
- `flip()` switches the buffer from write mode to read mode by setting `limit = position; position = 0`.
- `compact()` copies bytes in `[position, limit)` to the beginning and prepares for further writing, **preserving the unconsumed portion**.
- `clear()` only resets position/limit and **does not safely preserve partial frames** for subsequent reads.
- `mark()` and `reset()` are useful when reading the header and discovering the payload is incomplete: reset the position back to **the start of the header** before compacting.
- `remaining()` reports how many bytes are available in the current mode, not the number of frames or bytes still in flight on the wire.
- `capacity()` is the buffer capacity, not the request length. Do not decode/parse bytes outside `[position, limit)` in read mode.

### Be Careful When the Header Is Read but the Body Is Incomplete

```text
Buffer in read mode:
[00 00 00 05][48 45]
[length = 5]   "HE" (missing "LLO")
```

If the parser calls `getInt()`, `position` has already moved past the 4-byte header. When it sees `remaining() < 5`, it must `reset()` to **the start of the header** before `compact()`. Otherwise, the next read will only have `HE...` and the parser will misinterpret it as a new header. Another option is a state machine that stores `expectedLength = 5` and transitions to `READ_BODY`; in that case, the header does not need to stay in the buffer, but the expected length must be preserved per connection.

Example parsing snippet in read mode:

```java
while (buffer.remaining() >= Integer.BYTES) {
    buffer.mark();               // start of frame
    int length = buffer.getInt();
    if (length < 0 || length > MAX_PAYLOAD) {
        throw new IOException("Invalid frame length");
    }
    if (buffer.remaining() < length) {
        buffer.reset();          // keep partial header + payload
        break;
    }
    byte[] payload = new byte[length];
    buffer.get(payload);
    dispatchFrame(payload);
}
buffer.compact();
```

**This is a code snippet** depending on `buffer`, `MAX_PAYLOAD`, and `dispatchFrame`. The `while` loop is necessary because a single read can contain **multiple** complete frames. The parser must continue until only partial bytes remain, rather than waiting for a new read event for bytes already sitting in the buffer.

## 7. How Connection A and B's Independent Data Evolves

Suppose every frame has a 4-byte header, and both A and B have separate state with initially empty buffers. As the event loop processes events, we get:

| Event | State A after parse/compact | State B after parse/compact | Completed Message |
| --- | --- | --- | --- |
| A receives `00 00` | 2 header bytes A | Empty | None yet |
| B receives `00` | Keeps 2 bytes A | 1 header byte B | None yet |
| A receives `00 05 41 4C` | 4 header bytes + 2 payload bytes `AL` | Keeps 1 byte B | None yet |
| B receives `00 00 04 42 45 54 41` | A still pending | B parses `BETA`, pending empty | BETA |
| A receives `50 48 41` | A parses `ALPHA`, pending empty | B still empty | ALPHA |

This is one **valid hypothetical event schedule**; TCP/the network does not guarantee ordering across different sockets. What matters is that **byte ordering on *each* socket** is preserved, and state is not mixed across sockets.

A broken design:

```java
// Wrong: one receive buffer for all clients, no per-connection pending state
static final ByteBuffer sharedInbound = ByteBuffer.allocate(4096);
// Wrong: A's pending length overwritten by B
static int expectedLength = -1;
```

Even when the event loop runs on **a single thread**, shared mutable state is still logically wrong: B's read event can interleave between two of A's read events. "Single-threaded" eliminates certain data races, but it **does not eliminate valid interleaving across multiple connections**.

## 8. Runnable Java 17+: Selector and Two Connections with Split Frames

The following program creates a TCP listener on loopback `127.0.0.1`, registers `OP_ACCEPT`, accepts two clients in order A then B, attaches **a separate `ConnectionState`** to each channel's `SelectionKey`, and has both clients send interleaved frame parts.

Test protocol:
- 4-byte big-endian `int` describing payload length.
- UTF-8 payload, limited to `MAX_PAYLOAD = 32` bytes.
- Each client sends exactly **one frame** so a simple invariant can be asserted at EOF.

When the parser sees a complete header but insufficient payload, it uses `mark()/reset()` to preserve the partial frame; `compact()` moves the partial data to the front of **that connection's buffer**. The program intentionally finishes sending B before A to clearly show there is no mixing between the two buffers.

Save to the exact file `SelectorStateDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
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
import java.util.Iterator;

public class SelectorStateDemo {
    private static final int MAX_PAYLOAD = 32;
    private static int nextId;
    private static int messages;
    private static int closed;

    static final class ConnectionState {
        final int id;
        final ByteBuffer inbound = ByteBuffer.allocate(4 + MAX_PAYLOAD);
        int frames;
        ConnectionState(int id) { this.id = id; }
    }

    private static byte[] frame(String text) throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(payload.length);
            out.write(payload);
        }
        return bytes.toByteArray();
    }

    private static void sendPart(SocketChannel channel, byte[] wire,
                                 int start, int end) throws IOException {
        ByteBuffer part = ByteBuffer.wrap(wire, start, end - start);
        while (part.hasRemaining()) channel.write(part);
    }

    private static void parse(ConnectionState state) throws IOException {
        ByteBuffer buffer = state.inbound;
        buffer.flip();
        while (buffer.remaining() >= Integer.BYTES) {
            buffer.mark();
            int length = buffer.getInt();
            if (length < 0 || length > MAX_PAYLOAD) {
                throw new IOException("Invalid length: " + length);
            }
            if (buffer.remaining() < length) {
                buffer.reset();
                break;
            }
            byte[] payload = new byte[length];
            buffer.get(payload);
            state.frames++;
            messages++;
            System.out.println("connection " + state.id + ": "
                    + new String(payload, StandardCharsets.UTF_8));
        }
        buffer.compact();
    }

    private static void service(Selector selector) throws IOException {
        if (selector.select(2000) == 0) {
            throw new IOException("Timed out waiting for channel event");
        }
        Iterator<SelectionKey> selected = selector.selectedKeys().iterator();
        while (selected.hasNext()) {
            SelectionKey key = selected.next();
            selected.remove();
            if (!key.isValid()) continue;
            if (key.isAcceptable()) {
                ServerSocketChannel listener = (ServerSocketChannel) key.channel();
                SocketChannel accepted;
                while ((accepted = listener.accept()) != null) {
                    accepted.configureBlocking(false);
                    accepted.register(selector, SelectionKey.OP_READ,
                            new ConnectionState(++nextId));
                }
            } else if (key.isReadable()) {
                SocketChannel channel = (SocketChannel) key.channel();
                ConnectionState state = (ConnectionState) key.attachment();
                int n = channel.read(state.inbound);
                if (n == -1) {
                    if (state.inbound.position() != 0) {
                        throw new EOFException("Partial frame on connection " + state.id);
                    }
                    if (state.frames != 1) {
                        throw new IOException("Expected one frame on connection " + state.id);
                    }
                    closed++;
                    key.cancel();
                    channel.close();
                } else if (n > 0) {
                    parse(state);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (Selector selector = Selector.open();
             ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.configureBlocking(false);
            listener.bind(new InetSocketAddress(loopback, 0));
            listener.register(selector, SelectionKey.OP_ACCEPT);
            int port = ((InetSocketAddress) listener.getLocalAddress()).getPort();
            try (SocketChannel a = SocketChannel.open(
                         new InetSocketAddress(loopback, port))) {
                service(selector); // accept A, connection 1
                try (SocketChannel b = SocketChannel.open(
                             new InetSocketAddress(loopback, port))) {
                    service(selector); // accept B, connection 2
                    byte[] aFrame = frame("ALPHA");
                    byte[] bFrame = frame("BETA");
                    sendPart(a, aFrame, 0, 2); // partial A header
                    service(selector);
                    sendPart(b, bFrame, 0, 1); // partial B header
                    service(selector);
                    sendPart(a, aFrame, 2, 6); // A header + 2 body bytes
                    service(selector);
                    sendPart(b, bFrame, 1, bFrame.length); // B complete
                    service(selector);
                    sendPart(a, aFrame, 6, aFrame.length); // A complete
                    service(selector);
                    a.shutdownOutput();
                    b.shutdownOutput();
                    while (closed < 2) service(selector);
                    System.out.println("messages=" + messages + " closed=" + closed);
                }
            } finally {
                for (SelectionKey key : selector.keys()) key.channel().close();
            }
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac SelectorStateDemo.java
java SelectorStateDemo
```

Verified stdout when running on loopback:

```text
connection 2: BETA
connection 1: ALPHA
messages=2 closed=2
```

If the OS disallows binding the socket, the loopback environment encounters an I/O error, or an event does not arrive within the 2-second timeout, the program may throw `IOException`. The example intentionally uses a timeout to avoid hanging in tests; the sample output assumes loopback TCP operations succeed.

### Why Does This Example Prove Independent State?

1. `listener.register(selector, OP_ACCEPT)` makes the event loop watch for new connections.
2. After each accept, the server creates `new ConnectionState(++nextId)` and attaches it via `accepted.register(..., OP_READ, state)`. A's ID is 1; B's ID is 2 because the program accepts sequentially.
3. `state.inbound` is an **instance** field, so A's and B's bytes cannot reside in the same buffer.
4. `parse(state)` only reads the buffer of the connection that currently has `OP_READ`. If the header/payload is incomplete, it resets position and compacts; it never dispatches a partial message.
5. B finishes sending before A, so `connection 2: BETA` appears first. A keeps its own `AL` fragment and completes `ALPHA` afterward.
6. `shutdownOutput()` produces EOF for the server after the sent bytes are processed; the server checks there is no partial frame left, then cancels the key and closes the channel.
7. The test requires exactly **one frame per connection**; that is a test assertion, **not** a limitation of Selector or TCP. Real servers can receive thousands of frames per connection.

### What the Example Does Not Do for a Production Server

The example intentionally orchestrates each `sendPart(...); service(selector)` step so the interleaving schedule is easy to read and stdout is deterministic. A real server must run a long-lived event loop, handle many clients, send outbound responses, handle errors per connection, and enforce timeouts/quotas and backpressure. This case only demonstrates receiving and state ownership. The sections below explain how to extend it.

## 9. One Key Can Report Multiple Readiness Types in the Same Pass

Production event loops usually do not write `if (isReadable()) ... else if (isWritable()) ...` because a single key can **simultaneously** report both readable and writable. Handle each type appropriately, and re-check `key.isValid()` after any branch that might close the connection:

```java
if (key.isValid() && key.isConnectable()) {
    finishConnection(key);
}
if (key.isValid() && key.isReadable()) {
    readAndDecode(key);
}
if (key.isValid() && key.isWritable()) {
    flushPendingWrites(key);
}
```

This is a code snippet: the methods are application extension points, not built-in Java APIs. In a server listener, `OP_ACCEPT` usually lives on the `ServerSocketChannel` key and does not need client socket handling. A nonblocking TCP client using `OP_CONNECT` must call `finishConnect()` and then update `interestOps` to `OP_READ` or whatever ops are needed.

**When iterating `Selector.selectedKeys()`, remove the processed key from the selected set:**

```java
Iterator<SelectionKey> it = selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();
    if (!key.isValid()) continue;
    // dispatch based on ready ops
}
```

If you forget `it.remove()`, the old key can remain in the selected-key set and be reprocessed even when the event is no longer relevant, leading to a busy loop or unpredictable logic. Do not manually insert keys into the selected-key set; the selector manages readiness detection.

`SelectionKey.isValid()` can become false when the channel closes, the selector closes, or the key is canceled. A readiness event is only a hint and **does not guarantee** a single read/write always returns a positive byte count. Handle `0`, EOF, and exceptions properly.

## 10. Outbound State: Partial Writes Also Belong to Each Client

In nonblocking mode, `SocketChannel.write(ByteBuffer)` may write **fewer than all `remaining()` bytes** or return `0`. You must not assume a single `write` has sent the entire response. If A still has 200 response bytes left and B is waiting for another response, A's remaining bytes must stay in **A's outbound queue** with the updated `ByteBuffer.position`.

An extended state:

```java
static final class ConnectionState {
    final ByteBuffer inbound = ByteBuffer.allocate(4096);
    final Deque<ByteBuffer> outbound = new ArrayDeque<>();
    int queuedBytes;
    // protocol phase, deadline, request state...
}
```

This is an illustrative code snippet; you need to import `java.nio.ByteBuffer`, `java.util.Deque`, and `java.util.ArrayDeque`. Once the application has encoded a response frame:

```java
state.outbound.addLast(ByteBuffer.wrap(encodedFrame));
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
```

Here `encodedFrame` is an **exclusively owned** `byte[]`; do not mutate it after enqueuing unless a safe copy is made. Update `queuedBytes` accordingly, and ensure this is called on the thread managing the selector (or submit a task to the event loop and call `wakeup()`). Do not allow unbounded queues.

When the key reports writable:

```java
SocketChannel channel = (SocketChannel) key.channel();
ConnectionState state = (ConnectionState) key.attachment();
while (!state.outbound.isEmpty()) {
    ByteBuffer head = state.outbound.peekFirst();
    channel.write(head); // position advances automatically by bytes written
    if (head.hasRemaining()) {
        return;          // wait for next OP_WRITE, do not busy-write or reorder bytes
    }
    state.outbound.removeFirst();
}
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

This is an illustrative code snippet; production code needs to update `queuedBytes` by the number of bytes written, enforce per-pass time/byte budgets, and handle `IOException` by closing the affected connection. Only enable `OP_WRITE` when there is pending data; **sockets are normally always writable**, so leaving `OP_WRITE` permanently enabled when the queue is empty can cause a hot event loop and high CPU usage.

### Inbound and Outbound Are Related but Do Not Share State

A connection can simultaneously:
- Be partway through receiving the second request.
- Have finished processing the first request.
- Still have part of the first response left to write.
- Be waiting on a protocol handshake or asynchronous business processing.

Each I/O direction has its own state and buffer. Do not use the same `ByteBuffer` for both `channel.read` and `channel.write` on a connection without a clear ownership structure; and certainly do not share that buffer across multiple connections.

## 11. Protocol Phase and Parser State Are Connection Data

A real protocol can transition through states such as:

```text
ACCEPTED
  │
  ▼
HANDSHAKE / AUTHENTICATING
  │ success
  ▼
ACTIVE
  │
  ├── READ_HEADER -> READ_PAYLOAD -> DISPATCH -> READ_HEADER
  │
  ├── QUEUED_WRITE -> PARTIAL_WRITE -> COMPLETE_WRITE
  │
  └── CLOSING -> CLOSED
```

**Two distinct sets of state:**
- **Protocol phase:** has the client authenticated yet, sent the magic/version yet, is it awaiting handshake, or is it closing?
- **Frame decoder phase:** how many header or payload bytes are needed? How many bytes remain to complete a frame?

They can be stored as enums and remaining byte counts inside `ConnectionState`. A client in the handshake phase must not share a phase variable with an authenticated client. When using a finite state machine, transition phases only when **that connection's** required data is complete and passes validation.

For example, an application protocol requires `HELLO` before allowing `DATA`: if A sends `HEL` (incomplete) and B sends `HELLO` (complete), only B may transition to `ACTIVE`. Do not change A's phase just because B completed its handshake.

State can also store a `requestId` or a map of logical streams if a connection supports multiple concurrent requests. When multiplexing, you need a **state layer keyed by stream ID** inside the connection itself, rather than creating a new selector key per request. Keys are per channel; application requests do not turn into channels on their own.

## 12. Nonblocking Outbound Connections: OP_CONNECT and finishConnect

For a server accepting clients, `OP_ACCEPT` yields an already-accepted `SocketChannel`. When an application initiates nonblocking outbound connections to a remote peer, there is an additional **connecting** state:

```java
SocketChannel channel = SocketChannel.open();
channel.configureBlocking(false);
boolean connected = channel.connect(remote);
int ops = connected ? SelectionKey.OP_READ : SelectionKey.OP_CONNECT;
ConnectionState state = new ConnectionState(...);
SelectionKey key = channel.register(selector, ops, state);
```

This is a code snippet with `remote` (of type `SocketAddress`), `selector`, and the state class provided by the application. When `key.isConnectable()`, call `channel.finishConnect()` and handle the result or `IOException`. Once connected, register `OP_READ` and only enable `OP_WRITE` when there is outbound data. If the connection is not yet complete, calling read/write as if the socket were connected can throw `NotYetConnectedException`.

Store the **connection state** and **connect deadline** in that client's state, not in a shared `boolean connected` across all keys.

## 13. EOF, Half-Close, Errors, and Cleaning Up the Right Connection

`SocketChannel.read` returns `-1` when the peer has closed its sending side and no bytes remain to be read. This **does not automatically mean** all protocol frames are complete: EOF can arrive while the buffer holds 1–3 header bytes or a partial payload.

On EOF:
1. Let the parser consume any complete frames remaining in the buffer (if already-read bytes are held).
2. If a partial header/payload remains, report a **truncated frame** according to the protocol.
3. If the application allows TCP half-close, consider continuing to flush outbound responses before closing completely; otherwise, close according to the defined lifecycle.
4. Cancel the key, close the channel, clear references/queues, release resources, and decrement connection/memory counters.
5. Do not clear or reset another client's state.

The demo in section 8 closes immediately after receiving exactly one frame per client because that is the test's goal. In production, sometimes a request has been fully read while the response is still waiting for `OP_WRITE`; closing immediately upon reading EOF can drop the response. Clearly define whether the protocol allows half-close and whether pending writes must flush before closing.

A conceptual cleanup helper:

```java
static void closeClient(SelectionKey key) {
    try {
        key.cancel();
        key.channel().close();
    } catch (IOException ex) {
        // log or record metrics per policy
    } finally {
        // if maps/queues/timers exist outside the attachment: release them here
        key.attach(null);
    }
}
```

This is a code snippet used where key ownership is held; in a real system you must cancel timers, remove map entries, release pooled buffers, discard pending tasks, and complete response callbacks properly. `key.cancel()` requests deregistration; the key may only be removed from the selector's key sets on the subsequent select pass. `key.channel().close()` releases the socket/channel. **Closing a Selector does not guarantee closing all registered channels**, so server shutdown must actively close connections/channels.

### Exceptions Should Only Fail the Affected Connection

If B sends a negative length or a payload exceeding the maximum, the server should reject and close **B**; A continues uninterrupted if A has no issues. One client's parser error must not crash the entire event loop and shut down the server. Wrap per-client operations in `try/catch`, log/record metrics with rate limits, and clean up the corresponding state. Severe selector infrastructure errors may require server shutdown, but distinguish them from invalid input from a single client.

## 14. Managing Selected Keys, Readiness, and Fairness

A Selector can report many keys at once; the event loop must balance across connections.

- For each readable key, read until `0` in nonblocking mode or up to a **byte/time budget** per pass. Do not let one client with continuous data monopolize the event loop indefinitely.
- For each writable key, flush up to a byte/operation quota and move to the next key. Keep the remainder in the outbound queue.
- When processing multiple keys, always `iterator.remove()` handled keys from `selectedKeys()`. Do not keep references to the selected-key set and reprocess them without knowing readiness has changed.
- `key.isReadable()` and `key.isWritable()` are readiness bits and can both be true at once. After the read branch closes the channel, check `key.isValid()` before the write branch.
- Do not run blocking business work, slow database queries, other network calls, or large file I/O directly on the event loop. If a worker pool is needed, hand off **immutable/owned message data** via a queue and apply results on the event loop according to the connection's lifecycle.

### Per-Connection Backpressure

A client that reads responses slowly can cause its `outbound` queue to grow without bound. Enforce explicit per-connection quotas:
- Max pending outbound bytes.
- Max pending frames awaiting processing.
- Timeout for connections making no progress.
- Rule to temporarily disable `OP_READ` when the processing side cannot keep up, then re-enable it once the queue drains.
- Global server limits to prevent a group of bad clients from exhausting memory.

When disabling `OP_READ`, there must be a mechanism to **re-enable** it (queue drained, handler finished, deadline). Leaving reads disabled permanently can cause logical hangs. When the outbound queue is empty, disable `OP_WRITE` to avoid busy spinning.

## 15. Memory and Frame Limits for Thousands of Connections

If each client is allocated `ByteBuffer.allocate(1_048_576)` (1 MiB) and there are 5,000 connections, inbound buffers alone require roughly 5 GiB, not counting write buffers, object overhead, TLS, and queues. Therefore, prefer:
- Each state having a **right-sized small** buffer or a buffer pool with clear ownership.
- Checking frame length before allocating/growing; e.g., ≤32 bytes is the demo's policy, not a general limit.
- Using an accumulator that can grow **up to a quota** or an incremental header/payload state parser to avoid allocating maximum memory upfront.
- Per-connection and global server quotas, plus timeouts to block clients sending one byte at a time very slowly.
- Dedicated outbound queues with limits and a reject/close policy if the client cannot receive responses fast enough.
- Cleaning up all pooled `ByteBuffer` instances, timers, tasks, attachments, sockets, and map entries when the connection closes.

**You cannot conclude a frame was truncated just because a read returned fewer bytes**. TCP does not drop the remainder like UDP; you must keep it and continue reading. However, if the parser uses `clear()` or a shared scratch buffer without moving pending bytes into per-connection state, already-received data can be overwritten by the application itself.

### Separating Logical State from Physical Memory When Pooling

A shared buffer pool can be used **to allocate/reuse memory regions**, but at any given moment each region holding pending bytes must have a **clear owner**. Do not conflate "shared pool" with "buffer currently being written to by all channels". When returning a buffer to the pool, ensure no consumer or worker still holds a `slice()/duplicate()` pointing into that region.

`ByteBuffer.slice()` and `duplicate()` have their own position/limit but share the backing data. If a worker holds a slice while the event loop calls `compact()` or `read()` over the backing buffer, the worker may see corrupted payload bytes. Either copy the payload or use controlled reference-counting/lifetimes.

## 16. Thread Safety: One Event Loop Owns ConnectionState

The simplest model: only the event loop thread mutates `ConnectionState`, `SelectionKey.interestOps`, inbound/outbound buffer positions/limits, and parser phase. Other workers can perform heavy work on a **copy of the data** and send results back to the event loop.

`ByteBuffer` and mutable queues/state are not inherently thread-safe under concurrent modification. `Selector` can be woken up from another thread, but that does not make all state mutations thread-safe. A common organization:

```text
Worker thread completes result
    │
    ▼
Concurrent queue holding command (connection ID, result)
    │
    ▼
selector.wakeup()
    │
    ▼
Event loop receives command, checks connection is still alive
    │
    ▼
Appends response to the right connection's outbound queue
    │
    ▼
Enables OP_WRITE for the corresponding key
```

**Do not directly reuse an old `SocketChannel` or `SelectionKey` if the connection was closed and an ID was reused**. Use a non-reused connection object/token, check `key.isValid()` and state lifecycle before applying async results. Do not assume that just because a handler started while the connection was alive, it is still alive when the handler finishes.

In multi-event-loop systems, assign each connection to one owning loop; all mutations to that connection's state must be routed to that loop or explicitly synchronized. Each loop has its own `Selector`, avoiding two threads reading/compacting the same buffer.

## 17. Common Design Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| One `static ByteBuffer` for all clients | Bytes overwritten/mixed across connections | Dedicated inbound state per key |
| One global `expectedLength` | B's header overwrites A's parse progress | Per-connection parser field |
| Allocating a new buffer on every OP_READ | Partial header/payload lost | Buffer/decoder persists across events |
| `clear()` after partial parse | Overwrites pending bytes | `compact()` or move to dedicated state |
| Parsing only one frame and stopping | Remaining buffered frames get stuck | Loop to parse all complete frames |
| Assuming `read()` always returns a full frame | Truncated messages or parse errors | Length-prefix + partial-read state |
| No frame size limit | Malicious peer declares huge length | Validate length before allocating/growing |
| Always enabling `OP_WRITE` | Busy loop, high CPU | Enable when queue has data, disable when empty |
| Ignoring partial writes | Response loses bytes/reorders data | Per-connection `ByteBuffer` queue preserving position |
| One unrouted server-wide outbound queue | Sends response to wrong client | Queue inside each connection's state |
| Forgetting `selectedKeys().iterator().remove()` | Reprocesses stale keys/events | Remove dispatched key from selected set |
| Closing Selector but forgetting channels | Leaks sockets and connection resources | Clean up each key/channel |
| Running long-running tasks on event loop | All clients stall | Worker pool with message ownership |
| Worker mutates ByteBuffer alongside event loop | Data race, corrupted position/bytes | Single owner or full synchronization |
| Not checking EOF mid-frame | Treats truncated message as valid | Check pending bytes/phase at EOF |

A subtle bug: receiving A's complete frame, passing `ByteBuffer.slice()` to a worker, and immediately calling `compact()` to keep reading. If the worker has not finished, the slice may see different bytes. Do not treat `slice()` as an immutable payload.

## 18. Testing Per-Connection State, Not Just Standalone Parsers

Important unit tests for a single-connection decoder:
1. 4-byte header split into 1+1+2 bytes.
2. Complete header but insufficient payload; parser must preserve either the header or the length state.
3. A single read containing 3 frames plus the first few bytes of the next frame.
4. A frame at exact max size; an oversized frame is rejected.
5. EOF mid-header or mid-payload must report an error.
6. Multi-byte UTF-8 payload split across reads; decode only after the full frame arrives.

Important integration tests for Selector:
1. Two clients A/B send interleaved headers and payloads like the section 8 example; A must not receive B's data and vice versa.
2. A sends a partial frame while B sends multiple complete frames; B is not blocked by A.
3. A disconnects mid-frame; only A's state is cleaned up, B keeps working.
4. A sends a malformed frame with negative/huge length; B continues to be served.
5. A reads responses slowly, A's outbound backs up; B continues sending/receiving normally.
6. Writable event where `write()` returns 0 or writes partially; queue and `position` are preserved.
7. Multiple connections accepted simultaneously; each has its own attachment.
8. Worker returns a result after the client has closed; do not enqueue response on an invalid key.
9. Event loop shutdown; all keys/channels/timers/queues/pooled buffers are released.
10. Vary chunking boundaries across the same wire stream; parser yields the exact same list of messages.

To test framing **deterministically**, encode wire bytes, split them at every possible boundary, feed them into each connection's dedicated decoder, and compare the decoded payloads. Do not rely solely on TCP loopback to "accidentally" produce partial reads; the OS may coalesce writes and hide bugs.

To test connection isolation, create multiple source pairs with distinct IDs/payloads; after processing, compare logs containing **connection ID** and each connection's frame list. Avoid inferring correctness from global log order: there is no arrival-order guarantee across sockets.

## 19. Implementation Workflow in a Real Server

A maintainable event loop design:

1. **Accept:** nonblocking `ServerSocketChannel` signals `OP_ACCEPT`; accept pending connections up to a quota.
2. **Initialize:** each accepted channel gets a new `ConnectionState`, inbound parser/buffer, outbound queue, quota, and deadline; attach to the key.
3. **Read:** on `OP_READ`, read into the right state's buffer. If `n > 0`, parse all complete frames; if `n == 0`, wait for readiness; if `n == -1`, handle EOF/half-close.
4. **Parse:** preserve partial header/payload, validate length and protocol phase; dispatch immutable/owned messages to handlers.
5. **Business processing:** run lightweight work in the loop or offload long work to workers; route results back to the right live connection.
6. **Write:** enqueue responses into the connection's state; enable `OP_WRITE`. On each writable event, write what fits, keep unsent bytes, and clear interest when the queue is empty.
7. **Flow control:** enforce inbound/outbound quotas, timeouts, max frame size, client count, fairness, and backpressure per state.
8. **Close:** when the protocol ends or errors occur, cancel the key, close the channel, release state/timers/queues, and remove map entries.
9. **Shutdown:** stop accepting new connections, handle or gracefully cancel existing connections; close all channels and then the selector.

Check three invariants during code review:
- **Isolation:** connection A's data cannot enter B's buffer/queue/phase.
- **Continuity:** across each `select/read/write` pass, incomplete bytes and protocol state remain intact.
- **Ownership:** every buffer/attachment is mutated by a single clear owner and released when the connection ends.

## 20. Self-Check Questions

**Q1.** Why does a single-threaded event loop still need separate `ByteBuffer`s for connections A and B?  
**A:** Because events from A and B can interleave. A shared buffer/`expectedLength` causes A's pending bytes to be overwritten by B even without two threads running concurrently.

**Q2.** Does `key.isReadable()` mean a frame is complete?  
**A:** No. It only indicates the channel is ready for reading (or EOF/error). You must rely on framing and that connection's parser state.

**Q3.** The buffer has a 4-byte header with length=5 and only 2 payload bytes. If the parser already called `getInt`, what must it do before `compact`?  
**A:** `reset()` to the start of the header to keep both the header and partial payload, or store `expectedLength` in per-connection state and keep only the payload bytes.

**Q4.** B sends a complete frame while A is still waiting for the last 3 payload bytes. Can B be dispatched immediately?  
**A:** Yes. B has its own buffer/state; processing B does not need to wait for A unless a shared business constraint is explicitly designed.

**Q5.** Why not leave `OP_WRITE` enabled all the time?  
**A:** Sockets are normally writable; the event loop would continuously receive writable events even with no pending responses, causing high CPU usage. Enable it when the queue has data and disable it when empty.

**Q6.** If `SocketChannel.write` writes only 100/500 bytes of A's response, where are the remaining bytes?  
**A:** In the `ByteBuffer` in A's outbound queue, with `position` pointing right after the 100 written bytes. The next writable event resumes from that position.

**Q7.** A worker returns a result for client A after A has closed. Should the old `SelectionKey` be used to enqueue it?  
**A:** No. Check state lifecycle and key validity; discard or handle per policy, and never send it to a new connection by mistake.

**Q8.** Does `Selector.close()` automatically close all registered `SocketChannel`s?  
**A:** You should not rely on that. Track and actively close each channel during cleanup/shutdown.

**Q9.** When is it still correct to use a shared scratch buffer?  
**A:** When all unprocessed bytes are transferred/copied into the connection's own state before the scratch buffer is reused, and ownership is guaranteed.

**Q10.** In the `SelectorStateDemo` example, why is `BETA` printed before `ALPHA` without a TCP ordering error?  
**A:** Because they are two **different** TCP connections. There is no completion-order guarantee between two connections; within each connection, bytes remain in order.

## 21. References

- Java SE 17 `Selector` — key sets, selected keys, and readiness mechanism: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html
- Java SE 17 `SelectionKey` — `attach`/`attachment`, `interestOps`, `OP_READ/WRITE/ACCEPT/CONNECT`, cancellation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html
- Java SE 17 `SocketChannel` — nonblocking `read/write` and `finishConnect`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html
- Java SE 17 `ServerSocketChannel` — nonblocking accept: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html
- Java SE 17 `ByteBuffer` — `flip()`, `compact()`, `mark()/reset()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- RFC 9293, Transmission Control Protocol — TCP byte-stream semantics: https://www.rfc-editor.org/rfc/rfc9293
