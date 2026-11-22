# Java NIO Practical Exercise: Building a Selector Loop for Simple TCP Communication

The goal of this exercise is to **build a TCP echo server using `Selector`**, without spawning a dedicated thread per connection. The server listens for TCP using `ServerSocketChannel`; each client is represented by a `SocketChannel` in non-blocking mode. A single **event-loop thread** calls `selector.select()` to handle `OP_ACCEPT`, `OP_READ`, and `OP_WRITE` in turn. Once it reads a line ending with `\n`, the server replies with `echo:<content>\n`.

This exercise uses **Java 17+**, runs entirely on the loopback address, picks an ephemeral free port automatically, and includes a small TCP client right inside the program to verify the data path. The illustrative code intentionally **handles one request and stops** so learners clearly see the lifecycle of the selector, sockets, keys, and buffers; subsequent extension sections explain how to turn it into a long-lived multi-client server.

Keep in mind before starting: **readiness is not completion**. `OP_READ` does not guarantee a full line; `OP_WRITE` does not guarantee sending the whole response. We must track per-connection state, check actual byte counts transferred, update `interestOps`, and clean up resources at the right time.

## 1. Learning Objectives and Expected Outcomes

After this lesson, you will be able to:

1. Open a `Selector` and `ServerSocketChannel`, bind TCP loopback, and register `OP_ACCEPT`.
2. Accept connections via `accept()`, set `SocketChannel.configureBlocking(false)`, and register `OP_READ`.
3. Write the event loop `select() → selectedKeys() → iterator.remove() → handle event`.
4. Store `ByteBuffer`, partially read data, and pending write buffers inside `SelectionKey.attachment()`.
5. Accumulate bytes up to the `\n` delimiter; never mistake a single TCP `read` for a complete message.
6. Enable `OP_WRITE` only when a response actually exists; retain the buffer via `hasRemaining()` and clear write interest once drained.
7. Handle `read()==0`, `read()==-1`, `accept()==null`, `IOException`, invalid keys, and channel closing.
8. Run an end-to-end test over loopback, verify stdout, and troubleshoot common bugs.
9. Distinguish a single-selector-loop server model from thread-per-connection, and identify the example's limitations.

**Expected output:** the program prints `reply=echo:ping`, proves at least two read passes and three write passes using intentionally small buffers, and confirms `roundtrip=true`.

## 2. Environment Setup

Requirements:

- JDK **17 or later**, with Java SE's `java.nio.channels` and `java.net`.
- A terminal with `javac` and `java` on `PATH`, permitted to open local loopback connections.
- No external libraries, Maven, Gradle, or databases needed.
- Save the source file as UTF-8; filename must match the public class `SelectorTcpEchoDemo.java`.

Verify:

```bash
java -version
javac -version
```

The commands above check your environment; the printed version depends on your installed JDK. On machines where loopback is disallowed or blocked by security policy, the program may throw `IOException`, which is not a bug in the `Selector` API.

To avoid port conflicts, the program **binds port 0**. The OS allocates an available TCP port. The client obtains the actual address via `listener.getLocalAddress()`, so there is no need to hardcode port 8080 or open a port on a public network.

## 3. Architecture Overview

```text
                  Java process: two threads in this demo
┌──────────────────────────────────────────────────────────────┐
│ Main thread (test client)                                    │
│                                                              │
│   Socket.connect(loopback, ephemeralPort)                    │
│        │                                                     │
│        ├── send bytes: "ping\n" ────────────────┐            │
│        │                                        │            │
│        └── read response until server closes ◄──┼──────┐     │
│                                                 │      │     │
│ Event-loop thread                               ▼      │     │
│   Selector.select(3000)                         │      │     │
│        │                                        │      │     │
│        ├── OP_ACCEPT → ServerSocketChannel.accept()    │     │
│        │                  └── register peer: OP_READ   │     │
│        ├── OP_READ → SocketChannel.read(ByteBuffer)    │     │
│        │              → accumulate until newline       │     │
│        │              → set OP_WRITE                   │     │
│        └── OP_WRITE → SocketChannel.write(reply) ──────┘     │
│                       → repeat until !hasRemaining()         │
│                       → close peer, exit loop                │
└──────────────────────────────────────────────────────────────┘
```

**Distinguish thread count:** the complete program has one *main thread* acting as the test TCP client and one *event-loop thread* acting as the server. **The server side does not create one thread per client.** It uses a single selector to monitor registered channels. Do not describe this demo as "the entire program has only one thread".

**Distinguish handles:**

| Component | What Does It Do? | Key State |
| --- | --- | --- |
| `ServerSocketChannel` | Binds and accepts TCP clients. | `OP_ACCEPT`; server socket does not read client payloads directly. |
| `SocketChannel` | Accepted TCP connection; reads/writes bytes. | `OP_READ`, `OP_WRITE`; per-client `ByteBuffer`. |
| `Selector` | Waits for and selects I/O operations ready to progress. | `keys()` and `selectedKeys()`. |
| `SelectionKey` | Registration link between a channel and a selector. | `interestOps()`, `readyOps()`, `attachment()`, `isValid()`. |
| `State` | In-progress data for each TCP peer. | `input`, `request`, and `output`. |
| `ByteBuffer` | Byte buffer with `position/limit/remaining`. | Must `flip/clear` in the right phase. |

## 4. Event Sequence and Interest Ops

Lifecycle of one request:

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

`interestOps` is **what the application wants to monitor**; `readyOps` is **the readiness observed** in a given selection pass. Neither is a byte count transferred. Always inspect the actual `read/write/accept` return values.

For example, the server does not express interest in `OP_WRITE` before a response exists. If `OP_WRITE` is enabled from the start and left on continuously, the socket is usually always "writable" even when the outbound queue is empty, causing the select loop to fire incessantly and burn CPU.

## 5. Complete, Compilable, and Runnable Java 17+ Program

Save the full source as **`SelectorTcpEchoDemo.java`**. The program consists of:

- `State`: a small input `ByteBuffer` (3 bytes), a request accumulator, and a pending output `ByteBuffer`.
- `serve`: the server event loop handling `OP_ACCEPT/READ/WRITE`, removing each selected key after handling.
- `main`: opens selector/server, binds loopback, spawns one event-loop thread, uses a blocking `Socket` as test client, waits for the thread to finish, and asserts the results.
- Counters proving **at least** two read passes and three write passes; in the demo, buffer limits are set explicitly to make partial I/O effects reproducible.

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

**Why doesn't the test print exact read/write counts?** With networking and selectors, OS scheduling can vary. The demo deliberately sets the input buffer to just 3 bytes while the request `"ping\n"` is 5 bytes long, so **at least two successful read calls** are required. The response `"echo:ping\n"` is 10 bytes long while each write is capped at 4 bytes, so **at least three successful write calls** are required. Actual call counts may be higher; checking a lower bound is the right, stable assertion.

Note that this program performs **a single request, a single connection**. It is not a production echo server, does not maintain state for multiple requests on the same socket, and does not handle graceful half-close, TLS, authentication, or total memory policies. The extension sections at the end show where changes are needed.

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

1. `Selector.open()` creates the current provider's selector. The application does not need to drive `epoll/kqueue/poll` directly.
2. `ServerSocketChannel.open()` creates a channel for accepting connections; before binding, it is not listening on your chosen port yet.
3. `InetAddress.getLoopbackAddress()` serves local connections only. Do not bind `0.0.0.0` in a demo unless you want external machines attempting to connect.
4. Port `0` asks the OS to pick an available port. `listener.getLocalAddress()` after binding gives the real assigned address/port.
5. `configureBlocking(false)` is **mandatory** before calling `register` on a selector.
6. `OP_ACCEPT` is the valid operation for `ServerSocketChannel`; not `OP_READ`. Reading payloads is handled by accepted `SocketChannel` instances.
7. `try-with-resources` closes the selector and listener upon leaving scope, including when exceptions occur.

**Common mistake:** calling `listener.register(selector, OP_ACCEPT)` while the channel is still in blocking mode, causing `IllegalBlockingModeException`. Or registering `OP_READ` on `ServerSocketChannel`, which is not in that channel type's `validOps()`.

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

This runs inside the event loop of the complete program.

**Why `while (accept() != null)`?** With a non-blocking server channel, one `OP_ACCEPT` readiness notification may correspond to multiple queued connections. Once all currently available connections have been accepted, `accept()` returns `null`, at which point we return to the selection loop. Never assume exactly one connection per ready key.

**Why `peer.configureBlocking(false)`?** A newly accepted socket is not automatically guaranteed to be non-blocking in the desired configuration; the mode must be set explicitly before registering with the selector.

**Why attach `new State()` per peer?** Each client needs its own input buffer and pending data; if peers shared one mutable `ByteBuffer` without protocol ownership, bytes from different connections could interleave.

In a real server, a burst of connections may require capping **accepts per loop**, client quotas, timeouts, backpressure, and error handling if registration fails. The demo keeps the loop simple because there is only one test client.

## 8. `OP_READ`: A Request Can Arrive in Multiple Parts

TCP provides a **byte stream**, not preserving the sender's `write` boundaries. The client sends `"ping\n"` in one `Socket.getOutputStream().write(...)` call, yet the server may read multiple chunks:

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

| Result | Meaning | How to Handle |
| --- | --- | --- |
| `n > 0` | Read `n` bytes and advanced `ByteBuffer.position()`. | Parse the newly read bytes; keep state if frame is incomplete. |
| `n == 0` | No bytes transferred right now. | Do not busy-spin CPU; wait for another `OP_READ`. |
| `n == -1` | Input EOF (peer closed its sending side). | Decide to close, handle half-close, or respond per protocol. |

The demo uses `ByteBuffer.allocate(3)`, calls `flip()` after reading to consume all received bytes, and then `clear()`. Because every byte is copied into `ByteArrayOutputStream request`, it **does not need `compact()` in this design**. If a parser operates directly on an input buffer holding an incomplete frame without copying into separate state, you must call `compact()` to preserve unprocessed bytes.

When `\n` is encountered, the program converts accumulated bytes to a UTF-8 `String`. This is the right moment to decode, because a UTF-8 character can be split across two reads, especially if the request contains Vietnamese characters or emojis. **Do not** call `new String(chunkBytes, UTF_8)` separately on each chunk and concatenate strings; that can corrupt split multi-byte characters.

The `4096`-byte limit before newline prevents a client sending endlessly without a delimiter from growing memory without bound. This caps only **one request**; a real server also needs per-line send timeouts and total memory limits across all peers.

## 9. `OP_WRITE`: Preserving Progress and Enabling Only When Needed

Once a newline is seen, the server prepares:

```java
state.output = ByteBuffer.wrap(
        ("echo:" + message + "\n").getBytes(StandardCharsets.UTF_8));
key.interestOps(SelectionKey.OP_WRITE);
```

This pattern switches interest completely from `OP_READ` to `OP_WRITE` because **the demo accepts only one line**, sends the response, and closes the socket. A multi-request echo server usually keeps `OP_READ` enabled alongside `OP_WRITE` while outbound data is pending, or pauses reading selectively for backpressure.

On a non-blocking socket, a single `write(ByteBuffer)` call can:

- Write all remaining bytes.
- Write only **a portion**.
- Write **0 bytes**, even if the key was just reported writable.

Therefore you must preserve `ByteBuffer.position()` across multiple writes and treat the response as finished only when `!state.output.hasRemaining()`:

```java
// Snippet: output prepared (read phase), peer is non-blocking.
int n = peer.write(state.output);
if (n == 0) {
    // Do not busy-spin; wait for another readiness event.
}
if (!state.output.hasRemaining()) {
    // Entire buffer was consumed by peer.write.
}
```

In the demo, to ensure partial writes are observed, we **temporarily cap `limit` on output** before each call:

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

This snippet is extracted from the demo. Narrowing `limit` does not force the OS to write exactly 4 bytes: it only sets an **upper bound** on how much that call may write. `FileChannel/SocketChannel.write` may still write fewer. `finally` restores the original limit while preserving the advanced position.

When pending data drains, the demo cancels the key/closes the peer and stops; a long-running server usually **clears `OP_WRITE`**:

```java
// Enable when queue has data:
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

// Clear when queue is empty, keeping OP_READ or other flags:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

This is an extension snippet for a persistent server. **Do not leave `OP_WRITE` enabled when there is no data**: sockets are usually writable, causing `select` loops to wake continuously and spike CPU even with no requests.

## 10. `selectedKeys()`: Reading Right, Removing Right

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

This is an **illustrative iteration snippet**, not a verbatim replacement for `serve`: the full demo intentionally throws if 3 seconds elapse with no events.

- `selector.keys()` is the registered key set; `selectedKeys()` is the set of keys selected with readiness.
- `iterator.remove()` removes **the key from the selected-key set** once retrieved. This set is not automatically cleared by the runtime just because your code invoked a handler.
- Do not retain an old key and assume `readyOps` stays valid at a future time; readiness can change after I/O calls.
- `key.cancel()` requests deregistration, but **does not substitute for `SocketChannel.close()`** when you own the socket.
- `key.isValid()` must be checked before operations prone to throwing `CancelledKeyException`. A handler might cancel/close a key mid-event.
- One key can be ready for multiple ops simultaneously; the demo uses `if (key.isReadable())` followed by `if (key.isValid() && key.isWritable())` rather than assuming only one bit is set.

`Selector.select()` can return 0 due to timeouts, wakeups, or other API-permitted conditions; real applications should not treat every 0 as a disconnect error. Application-level timeouts must track explicit deadlines instead of resetting indefinitely on any unrelated event.

## 11. Client Test: Blocking Client Verifying a Non-Blocking Server

The client test snippet in `main`:

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

This snippet comes from the program. The client uses a blocking `java.net.Socket` **deliberately** to keep the exercise focused: the goal is writing a **Selector-based server event loop**, without requiring the client to be non-blocking too.

`readAllBytes()` on a socket waits until EOF, because TCP is a stream. The demo **closes the peer on the server side after writing the full response**, so the client sees EOF and the read returns the complete response. In keep-alive/multi-request protocols, do not use `readAllBytes()` to wait for one reply line if the server keeps the socket open; the client must read up to `\n` or a length-prefix.

`setSoTimeout(3000)` bounds blocking read wait time so the demo does not hang forever on failure, though very slow CI environments may require raising the timeout per test policy. The port binds only on loopback, has no authentication, and should not be exposed directly to the internet.

`AtomicReference<Throwable>` forwards errors from the event-loop thread back to the main thread after `join()`. This is a simple choice for a demo; larger applications usually employ service lifecycles, futures, or structured exception supervision.

## 12. Lifecycle Management and Resource Cleanup

Four resource groups to track:

| Resource | Who Owns It? | When to Close? |
| --- | --- | --- |
| `Selector` | Server/event-loop component. | After the event loop stops or during coordinated shutdown. |
| `ServerSocketChannel` | Listener component. | When stopping new accepts, or when shutting down the server completely. |
| Client `SocketChannel` | Handler/connection manager. | When the demo request completes, on EOF, error, timeout, or close policy. |
| Blocking client `Socket` | Test harness. | After receiving and checking the response, or on exception. |

The demo uses `try-with-resources` for the selector, listener, and blocking client. On the server, `peer.close()` closes the socket once the output buffer is fully drained.

**Important:** `ByteBuffer.hasRemaining() == false` only means the bytes from the buffer were accepted by `write` per its contract; it **does not** prove the remote application successfully processed the response. Protocols needing business confirmation require an application-layer ACK.

In a multi-client server, shutting down must close **all** open accepted channels, not just the listener and selector. Closing the selector invalidates keys, but should not be relied upon to automatically close every registered socket. Maintain clear ownership lists, or close peers during key cleanup and ensure cleanup in a `finally` block.

## 13. Intentional Limitations of the Sample Program

The illustrative program truly works, yet several choices serve learning only:

1. **One request, one response, then close:** after sending one line, `finished=true`. To serve multiple clients, remove the server-wide stop condition and close only the relevant peer.
2. **Does not handle multiple frames in one read:** if a client sends two lines in a single chunk, the demo processes only the first line and may discard the rest. Production must retain remaining bytes and loop the parser.
3. **No multi-buffer outbound queue:** one connection needs only one `output`; a multi-request server needs a `Deque<ByteBuffer>` and processes buffers until the queue empties.
4. **Sending at most 4 bytes per call** is a way to test partial writes, not a performance optimization.
5. **3-byte input buffer** forces partial reads; production usually uses larger buffers, memory pooling, and load-based quotas.
6. **UTF-8 decoding via `new String(bytes, UTF_8)` after newline:** untrusted input needs a strict decoder when valid UTF-8 is required, plus CRLF rules if supported.
7. **4096-byte limit** applies only to requests before the delimiter. There is no per-client slow-loris timeout beyond the overall `select` timeout.
8. **One blocking client thread** tests the server; real multi-client behavior requires dedicated load tests.
9. **I/O errors stop the whole server:** the demo makes errors easy to observe. Production should close only the failing connection and keep serving other clients, except on unrecoverable system errors.
10. **No TLS, authentication, metrics, logging, or real graceful shutdown:** do not deploy as-is to production.

These limitations do not make the example incorrect; they define the **lab scope** so you do not mistake a minimal event-loop illustration for a high-load server.

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
  WRITE: write each buffer, preserve partial state, clear OP_WRITE when queue is empty
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

Requires importing `ArrayDeque` and `ByteBuffer`. The event loop typically **owns** these state objects on a single thread. If another thread wants to push data into the queue, it must use proper synchronization and wakeups.

### Steps to Move from Single Request to Multiple Requests

- Replace `finished=true` with logic closing **only** the completed `SocketChannel` while keeping the server event loop running.
- After the output queue empties, keep or re-enable `OP_READ` for the connection if the protocol allows new requests.
- Use a parser that processes multiple newlines in one chunk; do not discard bytes after the first newline.
- Retain an incomplete buffer/byte collection for unfinished requests, avoiding per-chunk UTF-8 decoding.
- When a frame arrives, enqueue the response while still respecting memory/outbound queue limits.
- Apply deadlines for idle connections, incomplete requests, and shutdown.
- Close all accepted channels when stopping the service.

**Never attach the same `State` instance to every key.** Buffers and parsers must belong to their specific connection so requests from two clients never mix.

## 15. Backpressure and Avoiding CPU Busy-Spinning

A non-blocking server can encounter slow-reading clients. When the outbound queue still has bytes and `socket.write` returns 0, do not spin:

```java
// Snippet for non-blocking SocketChannel.
while (!out.hasRemaining()) {
    // Do not use this loop to simulate waiting.
}
```

The snippet above is an **anti-pattern**: it can burn CPU or make no sense while output still has bytes. Replace with:

```java
// Snippet: key is still valid, out is the pending ByteBuffer.
if (out.hasRemaining()) {
    int n = peer.write(out);
    if (n == 0) {
        key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
        // Return to select loop, do not retry infinitely here.
    }
}
```

Pattern for a queue:

1. When a response is ready, push a `flip()`ped (or `wrap`ped) `ByteBuffer` into `outbound`.
2. Enable `OP_WRITE`.
3. When ready, try writing the head buffer. If partially written, keep its `position`. If finished, remove it from the queue and continue with the next buffer within workload budgets.
4. When the queue empties, **clear `OP_WRITE`**. If bytes remain, keep interest enabled.
5. Cap total pending bytes per client and server-wide. If exceeded, pause reading from that client, report overload, or close the connection per policy.

Backpressure is not just about performance: without limits, thousands of slow-reading clients can pin vast amounts of encoded bytes on the heap until the application runs out of memory.

## 16. `select()`, `selectNow()`, `wakeup()`, and Thread Ownership

Methods:

| API | Effect | Notes |
| --- | --- | --- |
| `selector.select()` | Waits until selection is ready or woken/closed. | Fits continuous server loops; needs shutdown and task-queue mechanisms. |
| `selector.select(timeoutMs)` | Waits up to a positive timeout; `0` means indefinite wait per API contract. | Demo uses 3000 ms to fail fast. |
| `selector.selectNow()` | Non-blocking check of selection state. | Avoid spinning continuously when idle. |
| `selector.wakeup()` | Wakes a blocking or soon-to-block select pass. | Does not by itself make sockets readable/writable. |
| `key.interestOps(mask)` | Updates the interest bitmask. | Do not accidentally clear `OP_READ` when enabling `OP_WRITE`. |

When the event loop runs on its own thread and a producer wants to send more bytes:

```java
// Snippet: from producer thread; tasks is a thread-safe queue.
tasks.add(() -> enqueueOutbound(connectionId, bytes));
selector.wakeup();
```

Upon waking, the event loop drains tasks and updates state for the connections it owns. `wakeup()` only wakes selection; it **does not send bytes** for the application. If a producer mutates a `ByteBuffer` or `ArrayDeque` owned by the event loop directly from another thread, explicit synchronization is needed to prevent races.

**Thread safety of `Selector`/`Channel` does not substitute for protocol-state consistency.** One clean strategy is having a single event-loop thread own all registrations, cancellations, queue mutations, and parsing/writing for a connection, while other threads submit messages/tasks via a queue.

## 17. Common Mistakes When Doing This Exercise

| Symptom | Cause | Fix |
| --- | --- | --- |
| `IllegalBlockingModeException` on register | Forgot `configureBlocking(false)` before `register`. | Configure non-blocking on both listener and accepted sockets. |
| `IllegalArgumentException` on interest mask | `OP_READ` on `ServerSocketChannel` or flag outside `validOps()`. | Register `OP_ACCEPT` on listener, `OP_READ/WRITE` on peer. |
| Server receives no request after accept | Forgot to register new `SocketChannel`. | `peer.register(selector, OP_READ, new State())`. |
| Handler keeps firing on the same old key | Missing `iterator.remove()` on selected key. | Remove key from selected set inside iteration loop. |
| High CPU when no data exists | Keeping `OP_WRITE` always on or spinning on `read/write==0`. | Enable `OP_WRITE` only with pending data; return to `select`. |
| Client receives truncated response | `write` transferred partially; buffer reset/cleared. | Keep position, loop across readiness events until `!hasRemaining()`. |
| Server treats one chunk as one line | TCP does not preserve request boundaries. | Accumulate bytes until newline or length-prefix. |
| Vietnamese/emojis turn into `` | Decoding UTF-8 with missing bytes across chunks. | Buffer bytes and decode after full frame, or use an incremental decoder. |
| Server responds too early | Mistook `OP_READ` for a complete request before newline. | Keep parser state until delimiter. |
| Client `readAllBytes()` hangs forever | Server keeps keep-alive socket open without sending EOF. | Client reads per framing, or server closes after reply per protocol. |
| `CancelledKeyException` | Key cancelled yet handler still reads ready/interest ops. | Check `isValid()` and stop handler after close/cancel. |
| `ClosedChannelException` | Using channel after `close()` or wrong lifecycle. | Manage ownership and cleanup cleanly. |
| Hardcoded port throws `BindException` | Another process holds the port. | For labs, bind port 0 and use `getLocalAddress()`. |
| Server only works locally | Loopback rejects remote connections. | Intentional safety policy; production binds per config with network protection. |
| One slow client stalls the server | Blocking handler or unbounded processing. | Budget work per key; offload heavy blocking/CPU tasks. |
| Sockets stay open after server stop | Only closed selector without tracking accepted channels. | Close each peer, listener, and selector per lifecycle. |

For debugging, log timestamps, connection IDs, bytes `read/write`, `position/limit/remaining`, ready ops, interest ops, pending outbound bytes, and close reasons. Do not log raw payloads containing sensitive data or perform heavy blocking logging inside the event loop.

## 18. Practical Testing Workflow

### Test A — Run Demo and Check Stdout

1. Save the file in UTF-8 with the exact filename.
2. Run `javac -encoding UTF-8 SelectorTcpEchoDemo.java` and verify exit code.
3. Run `java SelectorTcpEchoDemo`.
4. Verify `reply=echo:ping` and `roundtrip=true`.
5. Verify `read-calls>=2=true`, `write-calls>=3=true`.
6. If it times out, check TCP loopback/antivirus policy, JVM, and ports; do not downgrade the test goal to "ran without exceptions" while skipping round-trip verification.

### Test B — Vary Payload

Change the client payload from `"ping\n"` to `"hello\n"` and update the expected reply to `"echo:hello\n"`. Confirm the parser waits for newline and the response loses no bytes. To observe at least three write passes, retain the demo's 4-byte cap.

### Test C — Missing Newline

Have the client send `"partial"` without closing or sending a newline, then apply a timeout. The server must not declare the frame complete; the test must enforce a deadline. When the peer closes before newline, the demo reports `EOF before request completed`.

### Test D — Oversized Request

Send more than 4096 bytes without a delimiter. The demo server throws `IOException("Request is too long")`. In a production server, close only the **offending connection** and keep serving other connections instead of stopping the entire service.

### Test E — Unicode/UTF-8

Send `"Việt 😀\n"` as UTF-8 while keeping the 3-byte input buffer. The receiver must accumulate all bytes before decoding. Logical output is `"echo:Việt 😀\n"`. When using a strict decoder, malformed input must be rejected cleanly.

### Test F — Multiple Concurrent Clients

After extending the server so it does not stop after the first client, run 10–100 test clients on loopback, each sending multiple lines at varying paces. Verify no mixed state/responses, no starvation, no socket leaks, and no busy looping when all are idle. Add quotas and timeouts before scaling load higher.

### Test G — Graceful Shutdown

While connections are active, set a stop flag and call `selector.wakeup()`; stop accepting, drain queues with a deadline, close accepted peers, close the listener, and then close the selector. Verify the event thread does not hang, does not drop tasks outside policy, and closes all resources.

## 19. Follow-Up Lab Exercises

**Exercise 1 — Toggle `OP_WRITE` instead of closing the connection.** Keep the connection open after one response to accept the next line. When the queue empties, instead of closing the peer, return to `OP_READ` (or keep `OP_READ` continuously and clear `OP_WRITE` via bitmask). Verify CPU stays low when clients are idle.

**Exercise 2 — Handle multiple lines in a single read.** Have the client send `"one\ntwo\n"` in a single write. Replace the `break` after newline with a parser capable of emitting two responses. Retain bytes after the first newline instead of dropping them; test exact order `echo:one`, `echo:two`.

**Exercise 3 — Outbound queue and partial writes.** Replace `State.output` with `ArrayDeque<ByteBuffer>`. Send three small responses and cap each write to at most two bytes. Verify final data is neither lost nor duplicated even when responses span multiple write calls.

**Exercise 4 — Length-prefix header.** Replace newline framing with a 4-byte `ByteOrder.BIG_ENDIAN` payload length prefix. Accumulate the full header, validate length is non-negative and at most 4096, then read exact bytes; test a header split across two reads.

**Exercise 5 — Non-blocking client.** Write a client using `SocketChannel` with `OP_CONNECT`. When `isConnectable()`, call `finishConnect()`; enable `OP_READ/WRITE` for the application protocol only after connection succeeds. Handle exceptions when connection fails.

**Exercise 6 — Worker pool.** Upon completing a frame, offload CPU-heavy work to an executor and send the response back to the event loop via a thread-safe queue + `selector.wakeup()`. Never let worker threads mutate a `ByteBuffer` owned by the event-loop thread directly.

**Exercise 7 — Backpressure.** Cap outbound pending data at 64 KiB per connection. When a client reads too slowly, temporarily clear `OP_READ` or reject/quarantine per protocol; resume reading when the queue drops below a low-water mark to prevent oscillation.

**Exercise 8 — Protocol errors and timeouts.** Add deadlines for idle connections, incomplete frames, and response draining. Clients sending unterminated lines or malformed UTF-8 must receive explicit error handling rather than holding sockets indefinitely.

**Exercise 9 — Metrics and load testing.** Measure active clients, bytes read/written, pending buffers, zero-return `select` loops, and p95 response latency. Distinguish throughput, readiness, and completed requests; do not infer success from event counts alone.

**Exercise 10 — Controlled server shutdown.** Build a thread-safe stop control, call `selector.wakeup()`, cancel keys, close channels from the selector-owning thread, and `join` with a deadline. Verify zero leaked file descriptors and non-blocking shutdown.

## 20. Questions to Answer After Running

1. How do `ServerSocketChannel` and `SocketChannel` differ in role? Why does the listener use `OP_ACCEPT` instead of `OP_READ`?
2. Why must `configureBlocking(false)` be called before `register()`?
3. When `selector.select()` returns, does the count of ready keys tell you total bytes to read/write?
4. Why must `iterator.remove()` appear in the `selectedKeys()` loop?
5. Why does the handler inspect bytes up to newline instead of treating one `read` as one request?
6. Why can a 3-byte input buffer still read a 5-byte request?
7. Why does `key.interestOps(OP_WRITE)` work only for the single-request demo, yet risk dropping `OP_READ` in a multi-request server?
8. When `write(output)` returns 0, why must you not loop continuously until it writes?
9. How do `ByteBuffer.flip()` and `clear()` change position/limit? When is `compact()` required?
10. Does `key.cancel()` automatically close the `SocketChannel` and free all memory state?
11. If a client keeps the connection open after a response, what can `readAllBytes()` end up waiting on, and how should protocols handle it?
12. Why does the server side of the demo use **one event-loop thread**, even though the program also has a main thread acting as client?
13. Once the server finishes writing bytes, does it know whether the client application processed the response and committed business state?
14. When moving to production, what must be added for many clients, backpressure, timeouts, TLS, and graceful shutdown?

## 21. Checklist Before Marking the Exercise Complete

- `javac` succeeds and running `java SelectorTcpEchoDemo` throws no exception in a supported loopback environment.
- Server binds loopback and an OS-assigned port without exposing a public listener.
- Non-blocking listener is registered with `OP_ACCEPT`.
- Accepted non-blocking `SocketChannel` is registered with `OP_READ` and its own `State`.
- Every selected key is removed via `iterator.remove()`.
- Requests are considered complete only upon encountering `\n` within quota.
- Output is sent according to `ByteBuffer.position()/remaining()` across multiple writes.
- Server does not keep `OP_WRITE` enabled when no response is pending in a multi-request architecture.
- Client receives exact `echo:ping\n` and the test confirms `roundtrip=true`.
- Every socket, listener, and selector has a clear owner and close path.
- Understood that a single-request demo is not a production multi-client server.
- Know how to extend the parser/queue and handle `read==0/-1`, timeouts, connection errors, and shutdown.

## 22. References

- [Java SE 21 — Selector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html): selected-key set, selection, `selectNow`, `wakeup`, close.
- [Java SE 21 — SelectionKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html): interest/ready ops, attachments, cancellation.
- [Java SE 21 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): binding and non-blocking accept.
- [Java SE 21 — SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): read/write, blocking mode, connection lifecycle.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `flip/clear/compact`, `hasRemaining`, and buffer semantics.
- [Java SE 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8 and explicit charsets.

**Remember:** A `Selector` loop uses one event-loop thread to coordinate multiple TCP channels by **readiness**, without transferring data or completing requests automatically. Build servers properly by registering non-blocking channels, calling `select`, removing processed selected keys, holding per-connection state for partial bytes, enabling `OP_WRITE` only when needed, handling partial I/O, and closing resources according to their lifecycle. Once the lab runs cleanly, the next essential steps are multiple requests, bounded queues, timeouts, and graceful shutdown.