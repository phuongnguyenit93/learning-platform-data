# Blocking and Non-blocking Modes in Java NIO Networking

## 1. What Question Do Blocking and Non-blocking Answer?

In network programming, operations such as waiting for a connection, accepting a connection, receiving bytes, or sending bytes can take time depending on the OS, socket state, peer, and network speed.

**Blocking** and **non-blocking** describe how an I/O call behaves when the condition required to perform the operation is not yet ready:

- **Blocking I/O**: the call may hold the calling thread in a waiting state until the operation can make progress, finishes, hits EOF, or errors. This **does not mean** it always waits, or that a single call always transfers all bytes.
- **Non-blocking I/O**: the call does not wait indefinitely just for the I/O condition to become ready; it can return immediately **without transferring any bytes**. The application must decide when to retry, typically coordinating with `Selector` to receive *readiness* notifications.

For example, a server calling `ServerSocketChannel.accept()` when no client is present:

| Server channel mode | What can happen |
| --- | --- |
| Blocking (default) | `accept()` waits until a connection arrives or a termination/error condition occurs |
| Non-blocking | `accept()` immediately returns **`null`** if no connection is currently waiting to be accepted |

Unlike `accept()`, some non-blocking `read()` calls use **`0`** to report no bytes received. Never equate `null`, `0`, and `-1` — each API has its own contract.

Java NIO provides both models to suit the number of connections, execution model, scalability, and simplicity of the application.

## 2. Related Classes in NIO Networking

| Java Type | Role | Blocking/non-blocking relationship |
| --- | --- | --- |
| `ServerSocketChannel` | Listen for and accept TCP connections | Blocking or non-blocking `accept()` |
| `SocketChannel` | TCP connection; read/write via `ByteBuffer` | `connect()`, `finishConnect()`, `read()`, `write()` |
| `DatagramChannel` | Send/receive datagrams, typically UDP | `receive()` can return `null` if non-blocking and no datagram is available |
| `SelectableChannel` | Common interface for channels registerable with a selector | `configureBlocking(boolean)` and `isBlocking()` |
| `Selector` | Monitors registered channels and readiness events | `select()`, `select(timeout)`, `selectNow()` |
| `SelectionKey` | Represents a channel's registration with a selector | `OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, `OP_WRITE` |

**`FileChannel` is not a `SelectableChannel`** and cannot be switched to socket-style non-blocking mode via `configureBlocking(false)` or registered with a `Selector`. This is a key distinction between **Java NIO using buffers/channels** in general and **non-blocking network I/O using a selector**.

A new channel in the `SelectableChannel` hierarchy starts in **blocking mode** by API contract, unless your code explicitly switches it to non-blocking.

## 3. Switching Modes via `configureBlocking`

`SelectableChannel` provides:

```java
SelectableChannel configureBlocking(boolean block) throws IOException;
boolean isBlocking();
```

- `configureBlocking(true)`: requests blocking mode.
- `configureBlocking(false)`: requests non-blocking mode.
- `isBlocking()`: checks the current mode (for an open channel).

Example:

```java
ServerSocketChannel server = ServerSocketChannel.open();
System.out.println(server.isBlocking()); // true
server.configureBlocking(false);
System.out.println(server.isBlocking()); // false
```

This is an illustrative snippet and requires closing the channel properly. `configureBlocking` is a **per-channel-instance configuration**, not a global change across the entire JVM or all sockets at once.

There is an important constraint: **a channel registered with any selector cannot switch back to blocking mode while it remains registered**. Attempting `configureBlocking(true)` in that situation throws `IllegalBlockingModeException`. When calling `SelectionKey.cancel()`, deregistration may only be processed during the next selection cycle; do not cancel a key and immediately assume you can switch to blocking without synchronizing the lifecycle.

Additionally, **to register with a `Selector`, the channel must be in non-blocking mode**. Registering while still blocking throws `IllegalBlockingModeException`. That does not mean every non-blocking channel must be registered with a selector: you can poll directly, though unconditional repeated polling easily creates a busy loop.

## 4. Behavior of `accept`, `connect`, `read`, and `write`

### 4.1. `ServerSocketChannel.accept()`

- Blocking: may wait for a new connection.
- Non-blocking: returns a `SocketChannel` when a connection is pending; if none yet, returns **`null`**.

Consequence: always check the return value of `accept()` before calling methods on the accepted channel.

### 4.2. `SocketChannel.connect(remote)`

- Blocking: typically returns only after connection establishment completes or an error occurs; `connect` returns `true` if successfully connected.
- Non-blocking: may return **`false`** because the connection process has not finished yet. When the channel signals `OP_CONNECT`, call `finishConnect()` to complete the handshake; if `finishConnect()` still returns false, continue waiting appropriately.
- `OP_CONNECT` signals readiness to finish, **not a guarantee** that the connection will succeed: connection errors can surface through `finishConnect()`.

Do not perform application reads/writes as if the socket were definitely connected just because non-blocking `connect()` returned false. You must handle the pending-connection state.

### 4.3. `SocketChannel.read(dst)`

Assuming `dst` has remaining space, is not read-only, and the socket is connected:

| Result | Meaning |
| --- | --- |
| `n > 0` | Received `n` bytes; `dst.position()` increases by `n` |
| `n == 0` | No bytes received in this call; common in non-blocking mode when not yet ready |
| `n == -1` | The remote peer ended its sending side or EOF was reached |

**`0` is not EOF**. Nor should you assume `read` always fills `dst.remaining()`. TCP is a **byte stream** and does not preserve message boundaries: one logical packet can arrive across multiple `read` calls, and a single `read` can contain data from multiple application messages.

If the buffer is full (`dst.remaining() == 0`), first process the data and then `clear()` or `compact()` for the current cycle, instead of misinterpreting receiving no more bytes as "the peer closed the connection".

### 4.4. `SocketChannel.write(src)`

- Returns the number of bytes actually written from `[src.position(), src.limit())`.
- May write only **part** of the data, even in blocking mode; correct code must still handle the remaining bytes per contract.
- In non-blocking mode, may return `0` if more bytes cannot be written right now.
- `write` does not use `-1` to signal EOF; closed/errored connection conditions must be handled via exceptions and channel state.

A successful `write()` call means the data was accepted into the transport pipeline per the I/O contract; it **does not guarantee the peer application has read or processed the data**.

## 5. Blocking Does Not Mean Synchronizing the Entire Program

Imagine a thread serving a client through these steps:

```text
accept() --wait for connection--> read() --wait for bytes--> process
                                               |
                                               v
                                           write()
```

If the I/O calls are blocking, **the thread making the call** can wait. Other threads in the same JVM can still run. Therefore, "blocking I/O" does not mean "the entire application freezes", and "non-blocking I/O" does not automatically mean "parallel processing".

Blocking is typically well suited for:
- Simple applications with few concurrent connections.
- One dedicated thread per connection when resources and the execution strategy allow.
- Business code needing linear, readable, and easy-to-debug control flow.

Common trade-offs:
- If the connection count is large and many clients send no data for long periods, a one-platform-thread-per-client design can be resource-heavy.
- Requires managing timeouts, task cancellation, backpressure, and socket closure.
- An operation can wait for a long time if there is no progress and no termination mechanism designed.

**Non-blocking** lets a small number of threads coordinate many connections, but shifts complexity into managing per-connection state, selectors, buffers, and partial read/write cases. Do not assume switching to non-blocking speeds up every scenario by default.

## 6. Standalone Java 17+ Example: Blocking TCP

This example runs a server and client on loopback within the same JVM. The server uses `ServerSocketChannel.accept()` in blocking mode, the client sends the four ASCII bytes `PING`, and the server reads all four bytes before finishing. To avoid depending on log ordering between two threads, **only the main thread prints the result after the server task completes**.

**File `BlockingTcpDemo.java`:**

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BlockingTcpDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            ExecutorService pool = Executors.newSingleThreadExecutor();
            try {
                Future<String> response = pool.submit(() -> {
                    try (SocketChannel accepted = server.accept()) {
                        ByteBuffer bytes = ByteBuffer.allocate(4);
                        while (bytes.hasRemaining()) {
                            int n = accepted.read(bytes);
                            if (n == -1) {
                                throw new EOFException("Client closed early");
                            }
                        }

                        bytes.flip();
                        return StandardCharsets.US_ASCII
                                .decode(bytes).toString();
                    }
                });

                try (SocketChannel client = SocketChannel.open()) {
                    client.connect(server.getLocalAddress());
                    ByteBuffer outgoing = ByteBuffer.wrap(
                            "PING".getBytes(StandardCharsets.US_ASCII));

                    while (outgoing.hasRemaining()) {
                        client.write(outgoing);
                    }
                }

                String received = response.get(5, TimeUnit.SECONDS);
                System.out.println("Blocking server: "
                        + server.isBlocking());
                System.out.println("Noi dung nhan: " + received);
            } finally {
                server.close();
                pool.shutdownNow();
            }
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac BlockingTcpDemo.java
java BlockingTcpDemo
```

**Stdout when loopback connection and I/O succeed:**

```text
Blocking server: true
Noi dung nhan: PING
```

**Explanation:**

1. `bind(..., 0)` lets the OS allocate a free TCP port; there is no need to hardcode a port number, and we do not print it because it varies across runs.
2. The server keeps the default blocking mode. The pool task waits at `accept()` until the client connects.
3. The client uses `SocketChannel.open()` and `connect(...)` in default blocking mode, then writes all four bytes with a `hasRemaining()` loop.
4. The server keeps calling `read(bytes)` until all four bytes are received or EOF occurs. It does not assume a single `read` gets all four bytes.
5. `Future.get` ensures the main thread prints results only after the server finishes reading. The 5-second timeout is a wait limit on `get`, not an automatic per-socket-operation timeout; the demo is designed for a healthy loopback environment.

Building a real-world server requires shutdown mechanisms, timeouts, connection limits, thread management, and resource protection. This example only demonstrates blocking behavior and reading a full TCP message of known length.

## 7. Non-blocking: Attempting I/O When Progress Is Possible

For `ServerSocketChannel` or `SocketChannel`:

```java
channel.configureBlocking(false);
```

When switching to non-blocking, code must be ready to handle:
- `accept() == null` when no connection is waiting.
- `connect() == false` while connecting.
- `read() == 0` when no bytes have been received yet.
- `write() == 0` when no bytes could be transferred yet.
- `read() == -1` when EOF is encountered (completely distinct from 0).

A common mistake:

```java
while (channel.read(buffer) == 0) {
    // Do nothing.
}
```

This loop can continuously peg the CPU while no data is available. Nor is there any guarantee that a subsequent read will receive the entire message.

**Best practice:** Register the non-blocking channel with a `Selector` and act when the appropriate `OP_ACCEPT`/`OP_CONNECT`/`OP_READ`/`OP_WRITE` event fires. When a non-blocking call makes no progress, return control to the event loop, preserve incomplete state, and wait for the next notification.

## 8. `Selector`: Waiting for Readiness Across Many Channels

`Selector` is the mechanism for multiplexing selectable channels:

```text
Socket A (non-blocking) ---\
Socket B (non-blocking) ----> Selector ---> one event loop
ServerSocketChannel -------/
                            |
                            +-- accept when ready
                            +-- finishConnect when connection ready
                            +-- read when ready to read
                            +-- write when ready to write
```

General workflow:

1. Open a `Selector`.
2. Switch each monitored channel with `configureBlocking(false)`.
3. Register via `channel.register(selector, interestOps)` to obtain a `SelectionKey`.
4. Call `selector.select()` or `select(timeout)` to wait until at least one eligible channel has readiness, or return on timeout/wakeup.
5. Iterate through `selector.selectedKeys()`, process valid keys, and **remove each key from the `selectedKeys` set after handling it**.
6. Update `interestOps` according to actual state, and continue the event loop until the application reaches a stop condition.

**Readiness does not guarantee transferring a predetermined number of bytes.** Between the selector event and the I/O call, conditions may change. Non-blocking `read`/`write` can still return 0 and require the application to hold state until next time.

Common interest bits:

| Bit | Typically used with | When interested |
| --- | --- | --- |
| `SelectionKey.OP_ACCEPT` | `ServerSocketChannel` | A connection is waiting to be accepted |
| `SelectionKey.OP_CONNECT` | `SocketChannel` performing non-blocking connect | `finishConnect()` can be called |
| `SelectionKey.OP_READ` | Connected `SocketChannel` | Bytes can be read, or EOF/error/data received can be handled |
| `SelectionKey.OP_WRITE` | `SocketChannel` with pending outbound data | Can attempt to write remaining data |

Not every bit is valid for every channel. `ServerSocketChannel.validOps()` supports `OP_ACCEPT`; `SocketChannel` supports connect/read/write operations. Registering an invalid bit throws `IllegalArgumentException`.

**Do not leave `OP_WRITE` enabled continuously just because a socket is open.** A socket is usually writable almost continuously whenever the network buffer has room, causing the selector to wake up repeatedly and burn CPU. Only enable `OP_WRITE` when data is **prepared but not yet completely sent**, and clear this interest once no bytes remain to be written.

## 9. Standalone Java 17+ Example: Non-blocking Accept/Read with Selector

The following program opens a server on loopback in non-blocking mode, registers `OP_ACCEPT`, and uses a **blocking** client to send the ASCII string `HELLO`. The server's event loop uses `Selector` to accept the connection and read until all five bytes arrive. Using blocking mode on the client does not make the server blocking: **the mode is configured per channel**.

The example prints results only after receiving all the data, so it does not depend on whether `SELECT` fires once or multiple times. Wait time is bounded so the demo does not hang forever in a broken network environment.

**File `NonBlockingSelectorDemo.java`:**

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
import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public class NonBlockingSelectorDemo {
    public static void main(String[] args) throws IOException {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {

            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);

            try (SocketChannel client = SocketChannel.open()) {
                client.connect(server.getLocalAddress());
                ByteBuffer message = ByteBuffer.wrap(
                        "HELLO".getBytes(StandardCharsets.US_ASCII));

                while (message.hasRemaining()) {
                    client.write(message);
                }

                String received = null;
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(5);

                while (received == null) {
                    long remainingNanos = deadline - System.nanoTime();
                    if (remainingNanos <= 0) {
                        throw new IOException("Selector timeout");
                    }

                    long timeoutMillis = Math.max(1L,
                            TimeUnit.NANOSECONDS.toMillis(remainingNanos));
                    selector.select(timeoutMillis);

                    Iterator<SelectionKey> keys =
                            selector.selectedKeys().iterator();

                    while (keys.hasNext()) {
                        SelectionKey key = keys.next();
                        keys.remove();

                        if (!key.isValid()) {
                            continue;
                        }

                        if (key.isAcceptable()) {
                            SocketChannel peer = server.accept();
                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(selector, SelectionKey.OP_READ,
                                        ByteBuffer.allocate(5));
                            }
                        } else if (key.isReadable()) {
                            SocketChannel peer =
                                    (SocketChannel) key.channel();
                            ByteBuffer buffer =
                                    (ByteBuffer) key.attachment();

                            int n = peer.read(buffer);
                            if (n == -1) {
                                throw new EOFException("Peer closed early");
                            }

                            if (!buffer.hasRemaining()) {
                                buffer.flip();
                                received = StandardCharsets.US_ASCII
                                        .decode(buffer).toString();
                                key.cancel();
                                peer.close();
                            }
                        }
                    }
                }

                System.out.println("Server non-blocking: "
                        + !server.isBlocking());
                System.out.println("Noi dung nhan: " + received);
            }
        }
    }
}
```

Compile and run:

```bash
javac NonBlockingSelectorDemo.java
java NonBlockingSelectorDemo
```

**Stdout when loopback and I/O succeed:**

```text
Server non-blocking: true
Noi dung nhan: HELLO
```

**Key points to understand:**

1. `server.configureBlocking(false)` is mandatory before `server.register(selector, OP_ACCEPT)`.
2. The selector waits for accept readiness, then `server.accept()` returns a new channel or possibly null; the program checks for null.
3. The new channel is also switched to non-blocking before registering `OP_READ`.
4. `read(buffer)` may read partially. Since the buffer has capacity 5, the event loop keeps the buffer as an attachment and continues until all five bytes arrive.
5. `selector.selectedKeys()` is the set of selected keys; the code uses `Iterator.remove()` to avoid improperly re-processing stale keys.
6. The demo does not use `OP_WRITE` because the client sends data in blocking mode. A production server handling non-blocking writes needs to manage a buffer queue and toggle `OP_WRITE` based on unsent data.
7. The demo assumes an exact five-byte message. Real applications need **framing** (e.g., length prefix, delimiter, or protocol parser), limits on message size, memory, and connection counts to avoid partial reads or misinterpreting data.

## 10. Non-blocking Connection Lifecycle and `OP_CONNECT`

A non-blocking client has an extra *connection in progress* phase:

```text
SocketChannel.open()
      |
      v
configureBlocking(false)
      |
      v
connect(address)
      |
      +--- true ---> connected; register OP_READ when needed
      |
      +--- false --> register OP_CONNECT
                         |
                         v
                  selector reports connectable
                         |
                         v
                    finishConnect()
                         |
                         +--- true --> connected
                         |
                         +--- false --> keep waiting
```

Illustrative code skeleton:

```java
SocketChannel socket = SocketChannel.open();
socket.configureBlocking(false);
boolean connected = socket.connect(remoteAddress);

if (connected) {
    socket.register(selector, SelectionKey.OP_READ);
} else {
    socket.register(selector, SelectionKey.OP_CONNECT);
}

// In the event loop, only when key.isConnectable():
// if (socket.finishConnect()) {
//     key.interestOps(SelectionKey.OP_READ);
// }
```

This snippet **is not a standalone program**; it requires declaring `remoteAddress`, `selector`, handling `IOException`, read/write events, and closing resources. `finishConnect()` can throw an exception if the connection fails; do not treat `isConnectable()` as a guarantee that connecting succeeded. If outbound data is waiting once connect finishes, you can also add `OP_WRITE` interest.

## 11. Partial Write and Backpressure in Non-blocking Mode

With a non-blocking socket, the send queue in the kernel or peer may not immediately accept more bytes. A call:

```java
int sent = socket.write(outgoing);
```

can return anything from 0 up to the number of bytes remaining in `outgoing`. Only the sent portion advances `outgoing.position()`. If `sent==0` or `outgoing.hasRemaining()` is still true, you must **retain the unsent data** to keep sending when `OP_WRITE` signals readiness.

One management pattern:

```text
Application creates response -> ByteBuffer in read mode
                                     |
                                     v
                                socket.write()
                                     |
                              +------+------+
                              |             |
                          All sent     Bytes remaining
                              |             |
                      clear OP_WRITE   enable OP_WRITE
                                            |
                                            v
                                     writable event
                                            |
                                            v
                                   try write again
```

Do not use an unconditional `while (outgoing.hasRemaining()) { socket.write(outgoing); }` loop on a non-blocking event loop if `write()` can keep returning 0: it causes a **busy spin**, blocking other connections. Instead, when not everything has been sent, retain the buffer and return to the selector.

**Backpressure** is the feedback mechanism when the consumer of data is slower than the producer. The event loop must bound the amount of pending data per connection (e.g., byte limits in the queue) and decide whether to pause reading, reject further requests, or drop the connection according to policy. Non-blocking does not eliminate memory pressure; it makes managing that pressure an explicit responsibility of the application.

## 12. `ByteBuffer.flip`, `clear`, and `compact` in Network I/O

Both modes use `ByteBuffer`; changing the blocking mode does not alter buffer rules.

| Step | Buffer state |
| --- | --- |
| Prepare to receive bytes | `clear()` → `position=0`, `limit=capacity` |
| Call `channel.read(buffer)` | `position` advances by actual bytes received |
| Prepare to decode/process | `flip()` → `limit=oldPosition`, `position=0` |
| Decode/consume | `position` advances by bytes processed |
| All processed | `clear()` to receive the next batch |
| Partially processed | `compact()` keeps the remainder before receiving more |

**`clear()` does not erase bytes from memory**. It only resets position and limit. If a parser still holds part of an incomplete message without enough bytes, `compact()` shifts the unprocessed portion to the start of the buffer, making room to receive more data into the trailing free space.

For UTF-8 or protocols where records span multiple receives, each `read` does not necessarily correspond to one string/row. You need a protocol-aware parser and a decoder capable of handling incrementally arriving data. The non-blocking example above uses fixed-length ASCII to isolate the blocking-mode topic, and should not be copied verbatim for arbitrary text handling.

## 13. Comparing Blocking and Non-blocking

| Criterion | Blocking | Non-blocking |
| --- | --- | --- |
| When I/O is not ready | Calling thread may wait | Call may return without progress |
| Control flow | Linear, easy to read | Event-driven/state machine, usually more complex |
| Common NIO tools | Blocking `SocketChannel`, `ServerSocketChannel` | `configureBlocking(false)` + `Selector` |
| Handling `read` results | Still must check byte count, EOF | Must check byte count, `0`, EOF |
| Handling `write` | Still must check partial write | Must retain pending bytes and wait for readiness |
| Cost of many idle connections | Multi-threaded model can consume significant resources | One event loop can manage many sockets |
| Design challenges | Threads, timeouts, cancellation, resource limits | Keys, connection state, buffers, backpressure, errors |
| Performance | Can be good for simple applications | Can be good for large numbers of mostly idle sockets |
| Nature | A way of performing I/O | A way of performing I/O; does not automatically mean asynchronous |

Choose the model based on specific requirements. If connection count is low and work is mostly sequential, blocking can be easier to maintain. If you must manage thousands of mostly event-waiting connections, non-blocking with a selector can be a better fit. Always **benchmark in a realistic environment** rather than asserting one mode is always faster.

## 14. How Does Non-blocking Differ from Asynchronous?

The two terms are frequently confused:

- **Non-blocking channel**: an I/O call may return immediately if no progress can be made yet. The application typically proceeds using `Selector`, readiness, and **explicit subsequent** I/O calls.
- **Asynchronous channel**: APIs such as `AsynchronousSocketChannel` use callbacks or `Future` to represent an ongoing or completed asynchronous operation. The completion mechanism belongs to the asynchronous API contract, not to non-blocking `SocketChannel.read` itself.

A non-blocking event loop can be structured in an "asynchronous" style at the application level, but calling `SocketChannel.configureBlocking(false)` does not turn the object into an `AsynchronousSocketChannel`. The two types have different APIs and completion models.

Furthermore, running a blocking call inside a `CompletableFuture` or a separate thread does not switch the **socket** itself to non-blocking mode; only task orchestration at the application layer changes.

## 15. Timeouts, Closing Connections, and Error Handling

Applications need clear policies for:
- **Incomplete connections**: connect timeouts; handling `finishConnect` failures.
- **Silent peers**: protocol/application-layer timeouts; non-blocking + selector timeout allows the event loop to evaluate deadlines.
- **Reading `-1`**: peer closed its sending direction; cancel interest and close or handle half-close per protocol.
- **Incomplete writes**: keep the pending buffer; do not release/`clear` prematurely.
- **Channel closed while in use**: catch and handle `IOException`/`ClosedChannelException` or specific errors.
- **Cancelled selector keys**: check `key.isValid()`; accessing `interestOps` or readiness on an invalid key can throw `CancelledKeyException`.
- **Closing resources**: use `try-with-resources` when ownership is clear, and manage the lifecycle of channels attached to a selector.

`selector.select(timeout)` is not a per-socket timeout. It is the readiness wait bound for **that selection call**, whereas business timeouts require tracking per-connection deadlines and checking them after each wakeup.

Do not assume every return from `select()` has useful I/O: a selector can wake up due to `wakeup()`, closing, interruption, or other conditions; check the number of ready keys and channel states before processing.

**Security:** When handling network data, bound request sizes, connection hold times, pending buffer volume, and connection counts. Never allocate unbounded buffers from client-supplied length headers without validation.

## 16. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Thinking non-blocking `read()==0` is EOF | Premature connection termination | Only `-1` is EOF in the read contract |
| Thinking blocking `read` always fills the buffer | Parser receives too few bytes | Track bytes read and use framing |
| Thinking `write` always sends all data | Unsent response portion lost | Keep `ByteBuffer` and continue from current position |
| Forgetting `configureBlocking(false)` before `register` | `IllegalBlockingModeException` | Configure non-blocking before registering |
| Calling `configureBlocking(true)` while still registered with a selector | `IllegalBlockingModeException` | Finish deregistering before switching mode |
| Calling non-blocking `accept()` without checking null | `NullPointerException` | Check result before using |
| Calling `read/write` before `finishConnect` completes | Invalid connection state | Handle `OP_CONNECT` and `finishConnect` |
| Looping tightly when `read/write == 0` | Busy spin, high CPU | Yield control back to Selector/event loop |
| Keeping `OP_WRITE` enabled with no pending data | Event loop wakes up constantly | Enable `OP_WRITE` only when writes are pending |
| Not removing keys from `selectedKeys()` | Re-processing stale events | Iterate with an iterator and call `remove()` |
| Treating one `read` as one TCP message | Broken framing | Design a clear protocol parser |
| Thinking `FileChannel` can register with a network selector | Wrong API type | Use an appropriate `SelectableChannel` |
| Closing buffer/peer with wrong lifecycle | Data loss or I/O errors | Design ownership, shutdown, and backpressure |

## 17. Check-up Exercises

**Question 1.** A non-blocking `SocketChannel` has `dst.remaining() == 128` and `read(dst)` returns `0`. Can we conclude the peer closed the connection?

**No.** `0` only indicates that the current call received no bytes; wait for `OP_READ` or an appropriate wait mechanism. Only `read` returning `-1` is EOF.

**Question 2.** `write(src)` returns 3 when `src.remaining()==10` initially. How many bytes remain to handle, and what should be done?

**7 bytes remain.** `src.position` increased by 3; do not `clear` early. If using non-blocking mode and more cannot be sent yet, keep the buffer, register interest in `OP_WRITE`, and try writing the remainder when ready.

**Question 3.** A `ServerSocketChannel` is registered with a `Selector`. Can `server.configureBlocking(true)` be called immediately?

**No.** While still registered with a selector, switching back to blocking throws `IllegalBlockingModeException`; you must properly manage deregistration, cancelled keys, and the selector lifecycle.

**Question 4.** Non-blocking `SocketChannel.connect(remote)` returns `false`. Is that a connection failure?

**No.** It may simply mean the connection is in progress. Register `OP_CONNECT`, call `finishConnect()` when ready, and handle any error if thrown.

**Question 5.** Why can a non-blocking server handle many connections on a single event loop yet still respond slowly?

**Because the event loop is still code running on a CPU.** If a handler performs long blocking work, heavy computation, or busy-spins when no I/O is ready, other connections will stall. Avoid blocking tasks on the event loop or offload heavy work to a separate controlled executor.

## 18. Key Takeaways

1. **Blocking**: an I/O operation may make the thread wait. **Non-blocking**: an operation can return immediately without progress.
2. **`configureBlocking(false)`** applies to `SelectableChannel`; new NIO network channels typically start in blocking mode.
3. **`accept()==null`**, **`read()==0`**, **`read()==-1`**, and **`connect()==false`** are **distinct** states that must be handled per contract.
4. **`Selector`** monitors `OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, and `OP_WRITE` readiness without busy-spinning.
5. **Partial read/write and `ByteBuffer.position/limit`** are the application's responsibility in both modes; in non-blocking mode you must retain remaining state and manage backpressure.
6. Blocking, non-blocking, and asynchronous are related concepts but **not synonymous**. Choose an architecture based on requirements, complexity, and real workload.

**Official reference:** Java SE 17 API — `java.nio.channels.SelectableChannel`, `ServerSocketChannel`, `SocketChannel`, `Selector`, `SelectionKey`, `java.nio.ByteBuffer`. Refer specifically to the Javadoc for `configureBlocking`, `register`, and the return values of `accept/read/write/connect/finishConnect`.
