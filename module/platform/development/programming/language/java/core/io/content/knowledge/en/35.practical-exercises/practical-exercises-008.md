# Java NIO Practice: Building a Selector Loop for Simple TCP Communication

The goal of this exercise is to **build a TCP echo server using `Selector`**, without spawning a dedicated thread per connection. The server listens for TCP via `ServerSocketChannel`; each client is represented by a `SocketChannel` in non-blocking mode. One **event-loop thread** calls `selector.select()` to handle `OP_ACCEPT`, `OP_READ`, and `OP_WRITE` in turn. Once a line ending in `\n` is read, the server replies with `echo:<content>\n`.

The exercise uses **Java 17+**, runs completely on the loopback address, picks an ephemeral free port automatically, and includes a small TCP client right inside the program to verify the data path. The illustrative code intentionally **handles one request and stops** so learners clearly see the lifecycle of selector, sockets, keys, and buffers; later extensions explain how to evolve it into a long-running multi-client server.

Keep in mind before starting: **readiness is not completion**. `OP_READ` does not guarantee a full line is ready; `OP_WRITE` does not guarantee the full response will be sent. We must maintain per-connection state, check actual bytes transferred, update `interestOps`, and clean up resources at the right time.

## 1. Learning Objectives and Expected Results

After this lesson, you will be able to:

1. Open a `Selector` and `ServerSocketChannel`, bind to TCP loopback, and register `OP_ACCEPT`.
2. Accept connections via `accept()`, call `SocketChannel.configureBlocking(false)`, and register `OP_READ`.
3. Write the event loop `select() → selectedKeys() → iterator.remove() → handle event`.
4. Store `ByteBuffer`, partial read data, and pending write buffers inside `SelectionKey.attachment()`.
5. Accumulate bytes up to the `\n` delimiter; never confuse one TCP `read` with one message.
6. Enable `OP_WRITE` only when a response actually exists; retain the buffer via `hasRemaining()` and clear write interest once drained.
7. Handle `read()==0`, `read()==-1`, `accept()==null`, `IOException`, invalid keys, and channel closing.
8. Run an end-to-end loopback test, verify stdout, and troubleshoot common mistakes.
9. Contrast a single selector-loop server with thread-per-connection, and identify the example's limits.

**Expected output:** the program prints `reply=echo:ping`, proves at least two read calls and three write calls thanks to intentionally small buffers, and confirms `roundtrip=true`.

## 2. Environment Setup

Requirements:

- JDK **17 or newer**, with standard Java SE `java.nio.channels` and `java.net`.
- Terminal with `javac` and `java` on `PATH`, permitted to open local loopback connections.
- No external libraries, Maven, Gradle, or database needed.
- Save the source file in UTF-8; filename must match the public class `SelectorTcpEchoDemo.java`.

Check:

```bash
java -version
javac -version
```

These are environment checks; printed versions depend on your installed JDK. On machines disallowing loopback or blocked by security policy, the program may throw `IOException`, which is not a Selector API bug.

To avoid port conflicts, the program **binds port 0**. The OS assigns an available TCP port. The client retrieves the real address via `listener.getLocalAddress()`, so there is no hardcoded port 8080 and no public network exposure.

## 3. Architectural Overview

```text
                  Java process: two threads in the demo
┌──────────────────────────────────────────────────────────────┐
│ Main thread (test client)                                    │
│                                                              │
│   Socket.connect(loopback, ephemeralPort)                     │
│        │                                                     │
│        ├── send bytes: "ping\n" ────────────────┐            │
│        │                                         │            │
│        └── read response until server closes ◄──┼──────┐     │
│                                                  │      │     │
│ Event-loop thread                                ▼      │     │
│   Selector.select(3000)                          │      │     │
│        │                                         │      │     │
│        ├── OP_ACCEPT → ServerSocketChannel.accept()     │     │
│        │                  └── register peer: OP_READ    │     │
│        ├── OP_READ → SocketChannel.read(ByteBuffer)     │     │
│        │              → accumulate until newline       │     │
│        │              → set OP_WRITE                    │     │
│        └── OP_WRITE → SocketChannel.write(reply) ──────┘     │
│                       → repeat until !hasRemaining()         │
│                       → close peer, exit loop                 │
└──────────────────────────────────────────────────────────────┘
```

**Distinguish thread counts:** the complete program has one *main thread* acting as the TCP test client and one *event-loop thread* acting as the server. **The server side does not spawn a thread per client**. It uses a single selector to monitor all registered channels. Do not describe this demo as "the whole program runs on a single thread".

**Distinguish handles:**

| Component | What Does It Do? | Key State |
| --- | --- | --- |
| `ServerSocketChannel` | Binds and accepts TCP clients. | `OP_ACCEPT`; server socket does not read client payloads directly. |
| `SocketChannel` | Accepted TCP connection; reads/writes bytes. | `OP_READ`, `OP_WRITE`; per-client `ByteBuffer`. |
| `Selector` | Waits for and selects I/O operations ready to progress. | `keys()` and `selectedKeys()`. |
| `SelectionKey` | Registration link between a channel and a selector. | `interestOps()`, `readyOps()`, `attachment()`, `isValid()`. |
| `State` | In-flight data for each TCP peer. | `input`, `request`, and `output`. |
| `ByteBuffer` | Byte buffer with `position/limit/remaining`. | Must `flip/clear` in the right phase. |

## 4. Event Flow and Interest Ops

Lifecycle of a single request:

```text
   server.bind(...)
      │
      ▼
   server.register(selector, OP_ACCEPT)
      │
      ▼
   Selector.select() ──────► key.isAcceptable()
                                      │
                             listener.accept() != null?
                               ├── no: return to select
                               └── yes:
                                   peer.configureBlocking(false)
                                   peer.register(OP_READ, State)
                                      │
                                 key.isReadable()
                                      │
                               peer.read(input)
                              /       |       \
                            >0       =0       -1
                            │         │        │
                     parse bytes    select   EOF/close
                            │
                     newline reached?
                       no       yes
                       │         │
                     select   create output
                                │
                           interestOps(OP_WRITE)
                                │
                           key.isWritable()
                                │
                           peer.write(output)
                             /        \
                       remaining     drained
                           │            │
                        select       close peer
                                       │
                                   stop demo
```

`interestOps` is **what the application wants to monitor**; `readyOps` is **the readiness observed** in one selection pass. They are not byte counts transferred. Always inspect the actual `read/write/accept` return values.

For example, the server does not watch `OP_WRITE` before having a response. Enabling `OP_WRITE` from the start and keeping it on causes the socket to stay almost always "writable" even with an empty queue, waking up the select loop continuously and burning CPU.

## 5. Complete Java 17+ Program, Compilable and Runnable

Save the whole listing as **`SelectorTcpEchoDemo.java`**. The program includes:

- `State`: a small input `ByteBuffer` (3 bytes), a request accumulator, and an output `ByteBuffer`.
- `serve`: the server event loop handling `OP_ACCEPT/READ/WRITE` and removing selected keys as processed.
- `main`: opens selector/server, binds loopback, starts exactly one event-loop thread, uses a blocking `Socket` test client, waits for the thread to finish, and asserts the results.
- Counters proving **at least** two read calls and three write calls; in the demo, buffer limits are set intentionally small to make partial I/O reproducible.

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.atomic.AtomicReference;

public class SelectorTcpEchoDemo {
    private static final class State {
        final ByteBuffer input = ByteBuffer.allocate(3);
        final ByteArrayOutputStream request = new ByteArrayOutputStream();
        ByteBuffer output;
    }

    private static final class Stats {
        int readCalls;
        int writeCalls;
    }

    private static void serve(Selector selector, Stats stats) throws IOException {
        boolean finished = false;
        while (!finished) {
            if (selector.select(3000) == 0) {
                throw new IOException("Server timed out");
            }
            Iterator<SelectionKey> iterator = selector.selectedKeys().iterator();
            while (iterator.hasNext()) {
                SelectionKey key = iterator.next();
                iterator.remove();
                if (!key.isValid()) continue;

                if (key.isAcceptable()) {
                    ServerSocketChannel listener =
                            (ServerSocketChannel) key.channel();
                    SocketChannel peer;
                    while ((peer = listener.accept()) != null) {
                        peer.configureBlocking(false);
                        peer.register(selector, SelectionKey.OP_READ,
                                new State());
                    }
                    continue;
                }

                SocketChannel peer = (SocketChannel) key.channel();
                State state = (State) key.attachment();

                if (key.isReadable()) {
                    int n = peer.read(state.input);
                    if (n == -1) {
                        peer.close();
                        throw new IOException("EOF before request completed");
                    }
                    if (n > 0) {
                        stats.readCalls++;
                        state.input.flip();
                        while (state.input.hasRemaining()) {
                            byte b = state.input.get();
                            if (b == '\n') {
                                String message = state.request.toString(
                                        StandardCharsets.UTF_8);
                                state.output = ByteBuffer.wrap(
                                        ("echo:" + message + "\n")
                                                .getBytes(StandardCharsets.UTF_8));
                                key.interestOps(SelectionKey.OP_WRITE);
                                break;
                            }
                            if (state.request.size() >= 4096) {
                                throw new IOException("Request is too long");
                            }
                            state.request.write(b & 0xff);
                        }
                        state.input.clear();
                    }
                }

                if (key.isValid() && key.isWritable()) {
                    // Only four bytes per call, to demonstrate partial writes.
                    int previousLimit = state.output.limit();
                    state.output.limit(Math.min(previousLimit,
                            state.output.position() + 4));
                    try {
                        int n = peer.write(state.output);
                        if (n > 0) stats.writeCalls++;
                    } finally {
                        state.output.limit(previousLimit);
                    }
                    if (!state.output.hasRemaining()) {
                        key.cancel();
                        peer.close();
                        finished = true;
                    }
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Stats stats = new Stats();
        try (Selector selector = Selector.open();
             ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            listener.configureBlocking(false);
            listener.register(selector, SelectionKey.OP_ACCEPT);

            Thread worker = new Thread(() -> {
                try {
                    serve(selector, stats);
                } catch (Throwable t) {
                    failure.set(t);
                }
            }, "selector-event-loop");
            worker.start();

            String reply;
            try {
                try (Socket client = new Socket()) {
                    client.connect(listener.getLocalAddress(), 3000);
                    client.setSoTimeout(3000);
                    client.getOutputStream().write(
                            "ping\n".getBytes(StandardCharsets.UTF_8));
                    reply = new String(client.getInputStream().readAllBytes(),
                            StandardCharsets.UTF_8);
                }
            } finally {
                worker.join(5000);
                if (worker.isAlive()) {
                    selector.close();
                    worker.join(5000);
                    throw new IOException("Event loop did not terminate");
                }
            }
            if (failure.get() != null) {
                throw new IOException("Event loop failed", failure.get());
            }
            System.out.println("reply=" + reply.stripTrailing());
            System.out.println("read-calls>=2=" + (stats.readCalls >= 2));
            System.out.println("write-calls>=3=" + (stats.writeCalls >= 3));
            System.out.println("roundtrip=" + reply.equals("echo:ping\n"));
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 SelectorTcpEchoDemo.java
java SelectorTcpEchoDemo
```

Stdout verified by compiling and running on JDK 17+ in an environment allowing TCP loopback:

```text
reply=echo:ping
read-calls>=2=true
write-calls>=3=true
roundtrip=true
```

**Why doesn't the test print exact read/write counts?** With networking and selectors, OS scheduling can vary. The demo deliberately sets the input buffer to just 3 bytes while the `"ping\n"` request is 5 bytes, so **at least two successful read calls** are needed. The response `"echo:ping\n"` is 10 bytes and each write is temporarily capped at 4 bytes, so **at least three successful write calls** are needed. Actual call counts may be higher; checking a lower bound is a more accurate and stable assertion.

Note that this program executes **a single request on a single connection**. It is not a production echo server; it does not keep state for multiple requests on the same socket, nor handle graceful half-close, TLS, authentication, or total memory policies. Extension sections at the end point out where changes belong.

## 6. Analyzing TCP Listener Initialization

Snippet in `main`:

```java
try (Selector selector = Selector.open();
     ServerSocketChannel listener = ServerSocketChannel.open()) {
    listener.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));
    listener.configureBlocking(false);
    listener.register(selector, SelectionKey.OP_ACCEPT);
}
```

This is an excerpt from the sample program. Technical points:

1. `Selector.open()` creates a selector for the current provider. The application need not control `epoll/kqueue/poll` directly.
2. `ServerSocketChannel.open()` creates an accepting channel; before binding, it is not listening on your chosen port.
3. `InetAddress.getLoopbackAddress()` serves local connections only. Do not bind `0.0.0.0` in a demo unless you want external machines attempting to connect.
4. Port `0` asks the OS to pick an available port. `listener.getLocalAddress()` after binding yields the actual address/port.
5. `configureBlocking(false)` is **mandatory** before calling `register` on a channel with a selector.
6. `OP_ACCEPT` is the valid operation for `ServerSocketChannel`; it is not `OP_READ`. Payload reading is handled by the accepted `SocketChannel`.
7. `try-with-resources` closes the selector and listener upon leaving scope, including when exceptions occur.

**Common mistake:** calling `listener.register(selector, OP_ACCEPT)` while the channel is still in blocking mode, causing `IllegalBlockingModeException`. Or registering `OP_READ` on a `ServerSocketChannel`, which is outside that channel type's `validOps()`.

## 7. `OP_ACCEPT`: From Server Socket to Client `SocketChannel`

Handler for a selected key with `isAcceptable()`:

```java
ServerSocketChannel listener =
        (ServerSocketChannel) key.channel();
SocketChannel peer;
while ((peer = listener.accept()) != null) {
    peer.configureBlocking(false);
    peer.register(selector, SelectionKey.OP_READ, new State());
}
```

This snippet runs inside the full program's event loop.

**Why `while (accept() != null)`?** On a non-blocking server channel, one `OP_ACCEPT` readiness event can correspond to multiple queued connections waiting to be accepted. Once all currently ready connections are accepted, `accept()` returns `null`, at which point control returns to the select loop. Never assume one ready key equals one connection.

**Why `peer.configureBlocking(false)`?** Newly accepted sockets are not guaranteed to be non-blocking under your desired setup; you must set the mode explicitly before registering with the selector.

**Why attach `new State()` per peer?** Each client needs its own input buffer and pending data; if peers share a mutable `ByteBuffer` without protocol ownership, bytes from different connections can interleave.

In a real server, a connection burst may require limiting **accepts per loop iteration**, client quotas, timeouts, backpressure, and error handling if registration fails. The demo keeps the loop simple since there is only one test client.

## 8. `OP_READ`: A Request Can Arrive in Multiple Parts

TCP provides a **byte stream**, preserving none of the sender's `write` boundaries. The client sends `"ping\n"` in a single `Socket.getOutputStream().write(...)` call, yet the server may read multiple chunks:

```text
Client sends five UTF-8 bytes:
70 69 6e 67 0a   = "ping\n"

Server input buffer has capacity 3:
1st read: 70 69 6e  -> "pin"
2nd read: 67 0a     -> "g\n"

Accumulated bytes before newline: 70 69 6e 67 = "ping"
Only after 0A is found: frame complete.
```

With non-blocking `SocketChannel.read(ByteBuffer)`:

| Result | Meaning | Handling |
| --- | --- | --- |
| `n > 0` | Read `n` bytes and advanced `ByteBuffer.position()`. | Parse the bytes just read, preserving state if frame is incomplete. |
| `n == 0` | No bytes transferred right now. | Do not spin CPU; wait for another `OP_READ`. |
| `n == -1` | EOF on input side (peer closed its send side). | Decide to close, handle half-close, or respond per protocol. |

The demo uses `ByteBuffer.allocate(3)`, calls `flip()` after reading to consume every received byte, and then `clear()`. Because every byte is copied into `ByteArrayOutputStream request`, it **does not need `compact()` in this design**. If running a parser directly on an input buffer holding an incomplete frame without copying elsewhere, you must call `compact()` to preserve unprocessed bytes.

Upon seeing `\n`, the program converts accumulated bytes into a UTF-8 `String`. This is the right moment to decode because a UTF-8 character can be split across two reads, especially when requests contain accented text or emojis. **Never** call `new String(chunkBytes, UTF_8)` on each chunk separately and concatenate strings; that corrupts split multi-byte characters.

The `4096`-byte limit before newline prevents a client sending endless bytes without a delimiter from growing memory unboundedly. That caps only **a single request**; real servers also need per-line send timeouts and global memory limits across all peers.

## 9. `OP_WRITE`: Keeping Progress and Enabling Only When Needed

Once a newline is observed, the server prepares:

```java
state.output = ByteBuffer.wrap(
        ("echo:" + message + "\n").getBytes(StandardCharsets.UTF_8));
key.interestOps(SelectionKey.OP_WRITE);
```

This pattern switches interest outright from `OP_READ` to `OP_WRITE` because **the demo accepts only one line**, then sends the reply and closes the socket. A multi-request echo server usually keeps `OP_READ` alongside `OP_WRITE` when outbound data is pending, or pauses reading in a controlled manner for backpressure.

On a non-blocking socket, a single `write(ByteBuffer)` call can:

- Write all remaining bytes.
- Write only **a portion**.
- Write **0 bytes**, even when the key just reported writable.

Hence `ByteBuffer.position()` must be preserved across multiple writes, considering the response completely written only when `!state.output.hasRemaining()`:

```java
// Snippet: output already prepared (read phase), peer is non-blocking.
int n = peer.write(state.output);
if (n == 0) {
    // Do not busy-spin; wait for next readiness.
}
if (!state.output.hasRemaining()) {
    // Entire buffer has been consumed by peer.write.
}
```

In the demo, to ensure partial writes are always observable, we **temporarily lower output's `limit`** before each call:

```java
int oldLimit = state.output.limit();
state.output.limit(Math.min(
        oldLimit, state.output.position() + 4));
try {
    peer.write(state.output);
} finally {
    state.output.limit(oldLimit);
}
```

This snippet comes from the demo. Narrowing `limit` does not ask the OS to write literally 4 bytes: it only sets an **upper bound** on what that call is allowed to write. `FileChannel/SocketChannel.write` may still write fewer. `finally` restores the old limit, while the advanced position stays intact.

Once pending data drains, the demo cancels the key / closes the peer and stops; long-lived servers instead **clear `OP_WRITE`**:

```java
// Enable when queue has data:
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

// Clear when queue is empty, keeping OP_READ or other flags:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

This is an extension snippet for persistent servers. **Never leave `OP_WRITE` enabled with no data to send**: sockets are normally writable, causing `select` loops to wake up continuously and spike CPU even with zero requests.

## 10. `selectedKeys()`: Reading and Removing Properly

Core event-loop pattern:

```java
while (!finished) {
    int selected = selector.select(3000);
    if (selected == 0) {
        // Demo: timeout. Real servers need timer/task policies.
        continue;
    }

    Iterator<SelectionKey> iterator =
            selector.selectedKeys().iterator();
    while (iterator.hasNext()) {
        SelectionKey key = iterator.next();
        iterator.remove();

        if (!key.isValid()) continue;
        // Check isAcceptable/isReadable/isWritable and handle.
    }
}
```

This is an **illustrative iteration snippet**, not a drop-in replacement for `serve`: the full demo intentionally throws on a 3-second timeout with no events.

- `selector.keys()` is the registered key set; `selectedKeys()` is the subset selected for readiness.
- `iterator.remove()` removes **the key from the selected-key set** after retrieving it. The runtime does not automatically remove keys just because your handler ran.
- Never cache an old key and assume `readyOps` remains accurate later; after I/O operations, readiness can change.
- `key.cancel()` schedules deregistration, but **does not replace `SocketChannel.close()`** when you own the socket.
- `key.isValid()` must be checked before operations that can throw `CancelledKeyException`. A handler may cancel/close a key mid-event.
- A single key can be ready for multiple ops simultaneously; the demo uses `if (key.isReadable())` followed by `if (key.isValid() && key.isWritable())` rather than assuming only one bit is set.

`Selector.select()` can return 0 due to timeout, wakeup, or other API-permitted conditions; in real applications, never treat every 0 return as a disconnect error. Application-level timeouts must track absolute deadlines rather than resetting endlessly on unrelated events.

## 11. Client Test: Blocking Client Testing a Non-Blocking Server

The test client in `main`:

```java
try (Socket client = new Socket()) {
    client.connect(listener.getLocalAddress(), 3000);
    client.setSoTimeout(3000);
    client.getOutputStream().write(
            "ping\n".getBytes(StandardCharsets.UTF_8));
    reply = new String(client.getInputStream().readAllBytes(),
            StandardCharsets.UTF_8);
}
```

This snippet is taken from the program. The client uses blocking `java.net.Socket` **deliberately** to keep the exercise focused: the goal is writing a **Selector-based server event loop**, not making the client non-blocking too.

`readAllBytes()` on a socket blocks until EOF, because TCP is a stream. The demo **closes the server-side peer after finishing the response**, so the client sees EOF and receives the whole reply. In keep-alive/multi-request protocols, never call `readAllBytes()` to wait for a single reply line if the server keeps the socket open; the client must read up to `\n` or a length prefix.

`setSoTimeout(3000)` bounds blocking read waits so the demo does not hang indefinitely on errors, though slow CI environments may need a higher test timeout. The port listens only on loopback, has no authentication, and must not be exposed verbatim to the internet.

`AtomicReference<Throwable>` carries any error from the event-loop thread back to the main thread after `join()`. This is simple for a demo; larger applications use service lifecycles, futures, or structured exception monitoring.

## 12. Lifecycle Management and Resource Cleanup

Four resource groups need attention:

| Resource | Who Owns It? | When to Close? |
| --- | --- | --- |
| `Selector` | Server/event-loop component. | After the event loop stops or is shut down. |
| `ServerSocketChannel` | Listener component. | When stopping new accepts or shutting down the server completely. |
| Client `SocketChannel` | Handler/connection manager. | When the demo request finishes, EOF, error, timeout, or close policy triggers. |
| Blocking client `Socket` | Test harness. | After receiving and checking the full reply, or on exception. |

The demo uses `try-with-resources` for the selector, listener, and blocking client. On the server side, `peer.close()` closes the socket once the output buffer is completely drained.

**Important:** `ByteBuffer.hasRemaining() == false` only means the bytes from the buffer were accepted by `write` per API contract; it **does not** prove the remote application processed the response successfully. Protocols needing business confirmation require an application-layer ACK.

In a multi-client server, shutting down must close **all** open accepted channels, not just the listener and selector. Closing the selector invalidates keys, yet you should not rely on it as an automatic close mechanism for all registered sockets. Maintain explicit tracking/ownership, or close peers via key handling and guarantee cleanup in a `finally` block.

## 13. Intentional Limitations of the Sample Program

The illustrative program runs for real, yet several choices serve learning purposes only:

1. **One request, one response, then close:** after sending one line, `finished=true`. To serve multiple clients, remove the server-wide stop flag and close only the corresponding peer.
2. **No multi-frame parsing per read:** if a client sends two lines in one chunk, the demo processes only the first and may drop the rest. Production code must retain leftover bytes and loop the parser.
3. **No multi-buffer outbound queue:** one connection holds just one `output`; a multi-request server needs a `Deque<ByteBuffer>` processed until empty.
4. **Sending at most 4 bytes per call** is for testing partial writes, not optimizing performance.
5. **3-byte input buffer** forces partial reads; production uses larger buffers, memory pooling, and load-based quotas.
6. **Decoding UTF-8 via `new String(bytes, UTF_8)` after newline:** for untrusted inputs, use a strict decoder when valid UTF-8 is required, plus CRLF rules if supported.
7. **4096-byte cap** covers only the request before the delimiter. There is no per-byte trickle timeout beyond the overall `select` timeout.
8. **Single blocking client thread** tests the server; real multi-client behavior needs dedicated load tests.
9. **Any I/O error stops the whole server:** helpful in a demo so learners see failures clearly. Production servers close the offending connection and keep serving other clients unless facing an unrecoverable system error.
10. **No TLS, authentication, metrics, logging, or real graceful shutdown:** do not deploy directly to production.

These limitations do not make the example wrong; they define a clear **lab scope** so you do not mistake a minimal event-loop demo for a high-load production server.

## 14. Scaling the Lab into a Multi-Connection Server

Model for maintaining multiple connections:

```text
Selector server
  ├─ ServerSocketChannel => OP_ACCEPT
  ├─ SocketChannel #1 => State(input, parser, outbound queue)
  ├─ SocketChannel #2 => State(input, parser, outbound queue)
  └─ SocketChannel #N => State(input, parser, outbound queue)

For each key:
  ACCEPT: accept up to quota then register OP_READ
  READ: read up to byte budget, decode multiple frames, enqueue responses
        if queue has data => enable OP_WRITE
  WRITE: write buffers one by one, preserve partials, clear OP_WRITE when empty
  EOF/ERROR: flush per protocol if needed, then close socket
```

A multi-request `State` might look like:

```java
// Design snippet, not a standalone runnable demo.
final class ConnectionState {
    ByteBuffer inbound = ByteBuffer.allocate(8192);
    ArrayDeque<ByteBuffer> outbound = new ArrayDeque<>();
    long lastActivityNanos = System.nanoTime();
    boolean peerInputClosed;
}
```

Imports for `ArrayDeque` and `ByteBuffer` are required. The event loop typically **owns** these state objects on a single thread. If another thread wants to push data into the queue, use proper synchronization and `wakeup()`.

### Steps from Single Request to Multiple Requests

- Replace `finished=true` with logic closing **only** the finished `SocketChannel` while the server event loop keeps running.
- After the output queue empties, keep/re-enable `OP_READ` on the connection if the protocol permits more requests.
- Use a parser that handles multiple newlines in one chunk; never discard bytes after the first newline.
- Retain an incomplete-request byte buffer/accumulator instead of decoding UTF-8 per chunk.
- When a frame arrives, enqueue the response while still enforcing memory and outbound-queue caps.
- Enforce deadlines for idle connections, incomplete requests, and shutdown.
- Close all accepted channels when stopping the service.

**Never attach the same `State` instance to multiple keys.** Buffers and parsers must be bound to their specific connection so requests from two clients never mix.

## 15. Backpressure and Avoiding Busy CPU Loops

A non-blocking server can encounter a slow-reading client. When the outbound queue still has bytes yet `socket.write` returns 0, do not spin:

```java
// Snippet for non-blocking SocketChannel.
while (!out.hasRemaining()) {
    // Do not use a loop like this to simulate waiting.
}
```

The snippet above is an **anti-pattern**: it can burn CPU or make no sense while output still has bytes. Replace with:

```java
// Snippet: key is still valid, out is the pending ByteBuffer.
if (out.hasRemaining()) {
    int n = peer.write(out);
    if (n == 0) {
        key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
        // Return to select loop; do not retry endlessly here.
    }
}
```

Pattern for the queue:

1. When a response is ready, push a flipped (or wrapped) `ByteBuffer` onto `outbound`.
2. Enable `OP_WRITE`.
3. When writable, try writing the head buffer. If partially written, keep its `position`. If fully written, pop it and continue to the next buffer within workload limits.
4. When the queue is empty, **clear `OP_WRITE`**. While bytes remain, keep the interest bit.
5. Cap pending bytes per client and server-wide. When exceeded, pause reading from that client, signal overload, or close the connection per policy.

Backpressure is not just about performance: without caps, thousands of slow-reading clients can accumulate gigabytes of encoded responses on the heap until the application runs out of memory.

## 16. `select()`, `selectNow()`, `wakeup()`, and Thread Ownership

Methods:

| API | Effect | Notes |
| --- | --- | --- |
| `selector.select()` | Blocks until selection is ready or woken up/closed. | Fits continuous server loops; needs shutdown mechanism and task queue. |
| `selector.select(timeoutMs)` | Waits at most a positive timeout; `0` waits indefinitely per API contract. | Demo uses 3000 ms to fail fast. |
| `selector.selectNow()` | Non-blocking check for selection readiness. | Do not spin continuously when idle. |
| `selector.wakeup()` | Wakes up a blocked or soon-to-block `select` call. | Does not itself make sockets readable or writable. |
| `key.interestOps(mask)` | Updates interest bitmask. | Do not accidentally clear `OP_READ` when setting `OP_WRITE`. |

When the event loop has its own thread and a producer wants to send more bytes:

```java
// Snippet: from producer thread; tasks is a thread-safe queue.
tasks.add(() -> enqueueOutbound(connectionId, bytes));
selector.wakeup();
```

Upon waking up, the event loop drains `tasks` and updates the state of connections it owns. `wakeup()` only unblocks selection; it **does not send bytes** on the application's behalf. If producers mutate event-loop `ByteBuffer`s or `ArrayDeque`s directly from another thread, explicit synchronization is required to avoid races.

**Thread safety of `Selector`/`Channel` does not replace protocol-state consistency.** An easy-to-reason-about strategy is letting a single event-loop thread own all registrations, cancellations, queue mutations, and parsing/writing for a connection, while other threads submit messages/tasks via a queue.

## 17. Common Pitfalls During Practice

| Symptom | Cause | Fix |
| --- | --- | --- |
| `IllegalBlockingModeException` on register | Forgot `configureBlocking(false)` before `register`. | Configure non-blocking on listener and accepted sockets. |
| `IllegalArgumentException` on interest mask | `OP_READ` on `ServerSocketChannel` or flag outside `validOps()`. | Register `OP_ACCEPT` for listener, `OP_READ/WRITE` for peers. |
| Server receives no requests after accept | Forgot to register the new `SocketChannel`. | `peer.register(selector, OP_READ, new State())`. |
| Handler keeps firing on the same old key | Missing `iterator.remove()` on selected key. | Remove key from selected set during iteration. |
| High CPU when idle | Keeping `OP_WRITE` always enabled or spinning on `read/write==0`. | Enable `OP_WRITE` only with pending data; return to `select`. |
| Client receives truncated reply | `write` sent only a portion; buffer was reset/cleared. | Keep `position`, loop across readiness events until `!hasRemaining()`. |
| Server treats one chunk as one line | TCP does not preserve request boundaries. | Accumulate bytes until newline/length-prefix. |
| Vietnamese/emoji turns into `�` | Decoding UTF-8 while bytes are missing across chunks. | Buffer bytes and decode after full frame, or use an incremental decoder. |
| Server replies too early | Assumed `OP_READ` meant full request before newline. | Keep parser state until delimiter. |
| Client `readAllBytes()` hangs forever | Server keeps socket open (keep-alive), sends no EOF. | Client reads by framing, or server closes after reply per protocol. |
| `CancelledKeyException` | Key cancelled yet handler keeps reading ready/interest ops. | Check `isValid()` and stop handler on close/cancel. |
| `ClosedChannelException` | Using channel after `close()` or wrong lifecycle order. | Manage ownership and cleanup cleanly. |
| Fixed port fails with `BindException` | Another process holds the port. | In labs, bind port 0 and read `getLocalAddress()`. |
| Server reachable only locally | Loopback blocks remote hosts. | Intentional safety policy; production binds per config and network security. |
| One slow client stalls the server | Blocking handler or unbounded work. | Budget work per key; offload heavy blocking/CPU work. |
| Server leaves sockets open after stop | Closed selector without tracking accepted channels. | Close each peer, listener, and selector per lifecycle. |

For debugging, log timestamps, connection IDs, `read/write` byte counts, `position/limit/remaining`, ready ops, interest ops, pending outbound bytes, and close reasons. Never log raw payloads holding sensitive data or perform heavy blocking logging inside the event loop.

## 18. Practical Testing Procedure

### Test A — Run Demo and Verify Stdout

1. Save the file in UTF-8 with the exact name.
2. Run `javac -encoding UTF-8 SelectorTcpEchoDemo.java` and verify exit code.
3. Run `java SelectorTcpEchoDemo`.
4. Verify `reply=echo:ping` and `roundtrip=true`.
5. Verify `read-calls>=2=true`, `write-calls>=3=true`.
6. On timeout, inspect TCP loopback/antivirus policy, JVM, and ports; do not weaken the test goal to "runs without exception" while ignoring the round-trip.

### Test B — Changing Payload

Change the client's message from `"ping\n"` to `"hello\n"`; update the expected reply to `"echo:hello\n"`. Ensure the parser waits for newline and the response loses no bytes. To keep testing at least three write calls, retain the demo's 4-byte cap.

### Test C — Missing Newline

Have the client send `"partial"` without closing or sending a newline, then apply a timeout. The server must not declare the frame complete; the test must have a deadline. When the peer closes before newline, the demo reports `EOF before request completed`.

### Test D — Oversized Request

Send more than 4096 bytes without a delimiter. The demo server throws `IOException("Request is too long")`. In a production server, close **the offending connection** and keep serving other connections instead of stopping the entire service.

### Test E — Unicode/UTF-8

Send `"Việt 😀\n"` as UTF-8, keeping the 3-byte input buffer. The receiver must accumulate all bytes before decoding. Logical output is `"echo:Việt 😀\n"`. With a strict decoder, malformed byte errors must be rejected cleanly.

### Test F — Multiple Concurrent Clients

After extending the server so it does not exit after the first client, run 10–100 test clients on loopback, each sending multiple lines at varying paces. Verify no mixed state/responses, no starvation, no socket leaks, and no busy-looping when all are idle. Add quotas and timeouts before ramping up heavy load.

### Test G — Graceful Shutdown

With active connections, set a stop flag and call `selector.wakeup()`; stop accepting, drain queues with a deadline, close accepted peers, close listener, then close selector. Verify the event-loop thread does not hang, drops no tasks outside policy, and closes all resources.

## 19. Advanced Post-Lab Exercises

**Exercise 1 — Toggle `OP_WRITE` instead of closing the connection.** Keep connections open after a reply to accept subsequent lines. When the queue empties, rather than closing the peer, return to `OP_READ` (or keep `OP_READ` continuously) and clear `OP_WRITE` via bitmask. Prove CPU stays near zero while clients are idle.

**Exercise 2 — Handle multiple lines in a single read.** Have the client send `"one\ntwo\n"` in one write. Replace the post-newline `break` with a parser that emits two responses. Retain bytes after the first newline instead of dropping them; verify order `echo:one`, `echo:two`.

**Exercise 3 — Outbound queue and partial writes.** Replace `State.output` with `ArrayDeque<ByteBuffer>`. Send three small replies and cap each write at 2 bytes. Verify final output loses/duplicates zero bytes across split writes.

**Exercise 4 — Length-prefix header.** Replace newline framing with a 4-byte `ByteOrder.BIG_ENDIAN` payload length header. Accumulate the full header, validate length is non-negative and `<= 4096`, then read the exact byte count; test a header split across two reads.

**Exercise 5 — Non-blocking client.** Write a client using `SocketChannel` with `OP_CONNECT`. On `isConnectable()`, call `finishConnect()`; enable `OP_READ/WRITE` for the application protocol only after connection succeeds. Handle connection failures.

**Exercise 6 — Worker pool.** When a complete frame arrives, offload CPU-intensive work to an executor, then send the response back to the event loop via a thread-safe queue + `selector.wakeup()`. Never let workers mutate event-loop `ByteBuffer`s directly.

**Exercise 7 — Backpressure.** Cap outbound pending data at 64 KiB per connection. When a client reads too slowly, temporarily clear `OP_READ` or reject/quarantine per protocol; resume reading only below a lower watermark to avoid rapid toggling.

**Exercise 8 — Protocol errors and timeouts.** Add deadlines for idle connections, incomplete frames, and response draining. Clients sending unterminated streams or malformed UTF-8 must trigger explicit error handling instead of holding sockets forever.

**Exercise 9 — Metrics and load testing.** Track active clients, bytes read/written, pending buffers, zero-result `select` cycles, and p95 response latency. Distinguish throughput, readiness, and completed requests; never infer success from event counts alone.

**Exercise 10 — Controlled server shutdown.** Build a thread-safe stop trigger, call `selector.wakeup()`, cancel keys, close channels on the selector's owning thread, and `join` with a deadline. Verify zero file-descriptor leaks and non-blocking shutdown.

## 20. Questions to Answer After Running

1. How do `ServerSocketChannel` and `SocketChannel` differ in role? Why does the listener use `OP_ACCEPT` instead of `OP_READ`?
2. Why must `configureBlocking(false)` be called before `register()`?
3. When `selector.select()` returns, does the ready key count tell you how many bytes will be read/written?
4. Why must `iterator.remove()` appear in the `selectedKeys()` loop?
5. Why does the handler inspect bytes up to newline instead of treating one `read` as one request?
6. How can a 3-byte input buffer still read a 5-byte request?
7. Why does `key.interestOps(OP_WRITE)` work only for the single-request demo, yet risk losing `OP_READ` in a multi-request server?
8. When `write(output)` returns 0, why shouldn't you loop immediately until it succeeds?
9. How do `ByteBuffer.flip()` and `clear()` change `position`/`limit`? When is `compact()` required?
10. Does `key.cancel()` automatically close the `SocketChannel` and release all memory state?
11. If a client keeps the connection open after a reply, what does `readAllBytes()` wait for and how should the protocol handle it?
12. Why does the demo's server side use **one event-loop thread**, even though the program also has a main thread acting as the client?
13. Once the server finishes writing bytes, does it know the client application processed the reply and committed business state?
14. When moving to production, what must be added for multiple clients, backpressure, timeouts, TLS, and graceful shutdown?

## 21. Completion Checklist

- `javac` succeeds and `java SelectorTcpEchoDemo` throws no exceptions in a loopback-enabled environment.
- Server binds loopback and an OS-assigned port without opening a public listener.
- Non-blocking listener is registered with `OP_ACCEPT`.
- Accepted non-blocking `SocketChannel` is registered with `OP_READ` and its own `State`.
- Every selected key is removed via `iterator.remove()`.
- Requests are treated as complete only upon `\n` within quota.
- Output is sent using `ByteBuffer.position()/remaining()` across multiple writes.
- Server never keeps `OP_WRITE` enabled without pending responses in multi-request architectures.
- Client receives exact `echo:ping\n`, and checks confirm `roundtrip=true`.
- Every socket, listener, and selector has a clear owner and close path.
- You understand that a single-request demo is not a production multi-client server.
- You know how to extend parsers/queues and handle `read==0/-1`, timeouts, connection errors, and shutdown.

## 22. References

- [Java SE 21 — Selector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html): selected-key set, selection, `selectNow`, `wakeup`, close.
- [Java SE 21 — SelectionKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html): interest/ready ops, attachments, cancellation.
- [Java SE 21 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): binding and non-blocking accept.
- [Java SE 21 — SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): read/write, blocking mode, connection lifecycle.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `flip/clear/compact`, `hasRemaining`, and buffer semantics.
- [Java SE 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8 and explicit charsets.

**Remember:** A Selector loop uses a single event-loop thread to coordinate multiple TCP channels by **readiness**; it does not transfer data or complete requests by itself. Build servers cleanly by registering non-blocking channels, calling `select`, removing processed selected keys, retaining per-connection state for partial bytes, enabling `OP_WRITE` only when needed, handling partial I/O, and closing resources per lifecycle. Once the lab passes, the key next steps are multi-request framing, bounded queues, timeouts, and graceful shutdown.
