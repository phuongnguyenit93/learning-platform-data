# Connect, finishConnect, accept, read, and write in Java NIO Networking

## 1. The Big Picture: From Connection Setup to Byte Exchange

Java NIO provides two key channels for TCP networking:

- `ServerSocketChannel`: **listens** at an address/port and calls `accept()` on an incoming TCP connection, producing a `SocketChannel` for the server side to exchange data.
- `SocketChannel`: represents a TCP connection; the client side uses `connect(...)`/`finishConnect()` to establish the connection, and both sides use `read(...)` and `write(...)` to receive/send bytes.

These channels can be used in two modes:

- **Blocking** (default): calls may wait until an operation can complete per contract, though a single `read` or `write` still does not necessarily process the entire buffer.
- **Non-blocking** (`configureBlocking(false)`): calls return when they cannot complete immediately; the program must retain state and continue later at an appropriate time, typically coordinated with `Selector`.

Typical flow:

~~~text
             SERVER                                  CLIENT
    ServerSocketChannel.open()                 SocketChannel.open()
               |                                        |
           bind(local)                                 |
               |                                  connect(remote)
               |                                        |
         accept() waits/yields                  [may be pending]
               |                                        |
       SocketChannel accepted                   finishConnect()
               |                                        |
               +----------- TCP connected --------------+
               |                                        |
         read() / write()                         write() / read()
               |                                        |
          close() / EOF                    shutdownOutput() / close()
~~~

`accept()` belongs only to `ServerSocketChannel`. `connect()` and `finishConnect()` belong to `SocketChannel`. Meanwhile `read()/write()` are used on the `SocketChannel` instances at **both ends of the connection**; TCP communication is bidirectional.

**Distinction to keep clear:** completing a connection is a different state from having data to read or space to write. `finishConnect() == true` does not mean the other side has sent data; `OP_READ`/`OP_WRITE` does not mean a complete application message is ready.

## 2. Open, bind, connect, and accept

### 2.1. Server side: bind then accept

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;

try (ServerSocketChannel server = ServerSocketChannel.open()) {
    server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
    System.out.println(server.getLocalAddress());

    try (SocketChannel peer = server.accept()) {
        // Use peer.read(...) and peer.write(...).
    }
}
~~~

This is an **illustrative snippet**, not a complete standalone example: place it in `main` or a method declaring/handling `IOException`, and a client must connect for the blocking `accept()` call to proceed.

- `ServerSocketChannel.open()` creates an unbound server channel.
- `bind(local)` selects the IP address and port to listen on. `port=0` asks the OS to assign an available port; `getLocalAddress()` returns the actual address after binding.
- `accept()` returns **a new `SocketChannel`** for the accepted connection. The server socket continues to be used for waiting on further connections; do not use it directly to read/write payload.
- The channel produced by `accept()` starts in **blocking mode**, even when `ServerSocketChannel` is configured as non-blocking. If you want to use it with a selector, you must explicitly call `peer.configureBlocking(false)` before registering.

When the server is in blocking mode, `accept()` normally waits until a connection arrives or an error/channel close occurs. In non-blocking mode, `accept()` **returns `null`** if no connection is currently ready to accept; `null` does not mean the server socket has closed.

Note: a server bound on loopback (`127.0.0.1`/`::1` depending on the environment) is only for local intra-machine communication. To accept connections from other machines, you need an appropriate bind address, network configuration, firewall, and security policy.

### 2.2. Client side: connect

~~~java
SocketChannel client = SocketChannel.open();
boolean connectedNow = client.connect(remoteAddress);
~~~

`remoteAddress` is a valid `SocketAddress` such as `new InetSocketAddress("localhost", port)`. After `connect(...)`:

| Client mode | Result of `connect(remote)` | Meaning |
| --- | --- | --- |
| Blocking (default) | Normally returns `true` if the connection is established; may block or throw `IOException`. | The connection is complete upon successful return. |
| Non-blocking | Returns `true` if completed immediately, or `false` if connecting is in progress. | If `false` is returned, the `finishConnect()` step remains before transferring data. |

`connect` does not mean "a complete connection already exists" in **non-blocking mode** when it returns `false`. At that point, `client.isConnectionPending()` may return `true`. To know whether it is truly ready to send/receive, use `isConnected()` or the result of `finishConnect()` in the appropriate cycle.

Exceptions can occur when the address is invalid, no route exists, the connection is refused, the port is blocked, the channel is closed, or the connect operation is invalid for the current state. For example, attempting to connect again when already connected can throw `AlreadyConnectedException`; when a connection is already pending, `ConnectionPendingException` can be thrown.

## 3. finishConnect(): Completing a Pending Connection

`SocketChannel.finishConnect()` completes a TCP connect process that was initiated but has not yet finished.

~~~java
client.configureBlocking(false);
boolean connected = client.connect(remoteAddress);
if (!connected) {
    // Later, when the channel is ready to finish connecting:
    connected = client.finishConnect();
}
~~~

This snippet illustrates the state flow. For a **non-blocking** client:

- `finishConnect() == true`: the connection is complete; `read`/`write` can begin.
- `finishConnect() == false`: still incomplete; preserve state, wait for the readiness event, and retry.
- Throws `IOException`: connection establishment failed.
- Calling it when no connection operation is pending and the channel is not yet connected can throw `NoConnectionPendingException`.

In **blocking mode**, `finishConnect()` may wait until the connection process finishes or an error occurs. In a non-blocking model, do not call it repeatedly in a `while` loop without a waiting mechanism because it easily causes a busy-spin.

### 3.1. Selector with OP_CONNECT

`Selector` lets you wait for one or more channels to report readiness. A simple pattern for non-blocking connect:

~~~java
// client and remoteAddress have already been created.
// This is an illustrative snippet, placed inside a method throws IOException.
client.configureBlocking(false);

boolean connected = client.connect(remoteAddress);
if (!connected) {
    try (Selector selector = Selector.open()) {
        SelectionKey key = client.register(selector, SelectionKey.OP_CONNECT);

        while (!client.finishConnect()) {
            int ready = selector.select(5_000);
            if (ready == 0) {
                throw new java.net.SocketTimeoutException(
                        "Không hoàn tất kết nối trong khoảng chờ");
            }

            selector.selectedKeys().clear();
        }
        key.cancel();
    }
}

// Only here should read/write be performed on the established connection.
~~~

Additional imports for this illustrative snippet: `java.nio.channels.Selector` and `java.nio.channels.SelectionKey`.

In the example, `selector.select(5_000)` may return after an event, timeout, wakeup, or other trigger; real-world applications handle events by inspecting each selected key and channel state. This snippet only demonstrates the lifecycle of **a single pending connection**, not a complete production selector pattern.

In a production event loop, you typically handle `key.isConnectable()` and call `finishConnect()`. On success, replace `interestOps` to remove `OP_CONNECT` and register desired operations such as `OP_READ` or `OP_WRITE`; always apply timeout, cancellation, and channel-closing rules if the connection fails.

### 3.2. Distinguishing OP_CONNECT and OP_ACCEPT

| Event | Registered channel | When ready |
| --- | --- | --- |
| `SelectionKey.OP_CONNECT` | `SocketChannel` performing non-blocking connect | Call `finishConnect()` to confirm completion; error handling may still be needed. |
| `SelectionKey.OP_ACCEPT` | Non-blocking `ServerSocketChannel` | Call `accept()` to obtain a `SocketChannel`; may return `null` if no pending connection remains. |
| `SelectionKey.OP_READ` | Connected `SocketChannel` | Call `read(...)`; may read a few bytes, `0`, or `-1`. |
| `SelectionKey.OP_WRITE` | Connected `SocketChannel` | Call `write(...)` when outbound data is waiting; may write partially or `0`. |

Readiness is only a hint **to attempt the operation**, not a guarantee that the entire I/O request will complete in one call.

## 4. accept(): Accepting a Pending Connection, Not Reading Data

A TCP server can accept many clients. Each successful `accept()` returns a separate `SocketChannel` representing that connection. This SocketChannel has two independent data directions following the TCP byte stream.

In non-blocking mode:

~~~java
try (ServerSocketChannel server = ServerSocketChannel.open()) {
    server.bind(new InetSocketAddress("127.0.0.1", 9000));
    server.configureBlocking(false);

    SocketChannel peer = server.accept();
    if (peer != null) {
        peer.configureBlocking(false);
        // Register OP_READ or continue managing in the event loop.
    }
}
~~~

This is an **illustrative snippet**; it needs `import java.net.InetSocketAddress;` and the corresponding channel APIs. Port 9000 is only for illustration; it may be occupied in a real environment.

If `accept() == null`, do not conclude the server has an error. It only indicates that **this non-blocking call** did not retrieve a connection. The event loop should wait for `OP_ACCEPT` to try again.

With a selector, a single `OP_ACCEPT` readiness event may have multiple pending connections; a common pattern is:

~~~java
if (key.isAcceptable()) {
    ServerSocketChannel listener = (ServerSocketChannel) key.channel();
    SocketChannel peer;

    while ((peer = listener.accept()) != null) {
        peer.configureBlocking(false);
        peer.register(selector, SelectionKey.OP_READ,
                new ClientState());
    }
}
~~~

This is **event-loop integration pseudocode**: `key`, `selector`, and `ClientState` must be defined by the application; `ClientState` can hold buffers and protocol state. A `while` loop like this is suitable when the listener is configured **non-blocking**; if the listener is blocking, calling `accept()` again can block indefinitely.

A real-world server must also enforce connection limits, idle timeouts, backpressure, application authentication, and stateful socket shutdown procedures.

## 5. read(): Reading Bytes from TCP into ByteBuffer

On `SocketChannel`, the syntax is:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);
int count = socket.read(buffer);
~~~

Here `socket` is a connected `SocketChannel`. Read results:

| Return value | Interpretation |
| --- | --- |
| `count > 0` | Exactly `count` bytes were copied into the buffer; `position` advances accordingly. |
| `count == 0` | No bytes were transferred in this call; common when non-blocking and no data is available yet. |
| `count == -1` | The peer closed its sending side (end-of-stream) and no further bytes remain to read. |

In blocking mode, a read with space remaining in the buffer typically waits for at least one byte, EOF, or an error; **it does not wait to fill the buffer**. In non-blocking mode, `read()` can return `0` very quickly. Do not infer from `0` that the connection is closed. `-1` indicates EOF on the read direction.

After `read(buffer)` writes bytes into the buffer, the program switches to reading from the buffer itself using `flip()`:

~~~java
int n = socket.read(buffer);
if (n > 0) {
    buffer.flip();

    while (buffer.hasRemaining()) {
        byte b = buffer.get();
        // Parse byte b.
    }

    buffer.clear();
} else if (n == -1) {
    // Peer closed its sending direction.
} else {
    // n == 0: no progress yet; wait for next readiness.
}
~~~

This is an **illustrative snippet** for the case where the application processes **all bytes just read**. If the parser only consumes part of a message, retain unprocessed bytes using `compact()` or an appropriate accumulation structure instead of calling `clear()` where they could be overwritten.

### 5.1. One read is not one message

TCP is a **byte stream**: it does not preserve boundaries between `write(...)` calls on the sender side. If the sender sends:

~~~text
[HEL][LO]
~~~

the receiver might observe:

~~~text
read #1: HELLO
~~~

or:

~~~text
read #1: H
read #2: EL
read #3: LO
~~~

Both conform to TCP. The application must provide **framing** such as packet length, delimiter, or record format. If a header is 4 bytes long, you must read all 4 bytes statefully rather than assuming a single `read` suffices.

### 5.2. When EOF arrives mid-frame

If 2 out of 4 header bytes have arrived and then `read() == -1`, that is an **incomplete/truncated message** under a fixed-length protocol. Conversely, when an application simply reads an entire stream until EOF, `-1` is the normal completion condition.

`SocketChannel.shutdownOutput()` allows one side to stop sending while continuing to read from the peer; this is a TCP **half-close**. `-1` on the read direction does not necessarily mean the application must immediately discard pending outbound data in the reverse direction; that decision belongs to the protocol.

## 6. write(): Sending Bytes from ByteBuffer to the Connection

`write(buffer)` takes bytes from **`position` up to `limit`** of the buffer and advances position by the number of bytes actually sent:

~~~java
ByteBuffer buffer = ByteBuffer.wrap(
        "PING".getBytes(StandardCharsets.US_ASCII));

int written = socket.write(buffer);
System.out.println("remaining=" + buffer.remaining());
~~~

This is an **illustrative snippet** assuming a connected `socket` and imports `java.nio.ByteBuffer`, `java.nio.charset.StandardCharsets`. The `remaining` output depends on how many bytes the socket consumed during that write call.

- `written > 0`: number of bytes accepted by the channel; more bytes may still remain to be sent.
- `written == 0`: no bytes were consumed; in non-blocking mode you typically wait for `OP_WRITE`.
- I/O errors are reported via exceptions. `write()` does not use `-1` to signal EOF like `read()`.

A suitable blocking pattern for sending the full buffer:

~~~java
static void writeFully(SocketChannel channel, ByteBuffer src)
        throws IOException {
    while (src.hasRemaining()) {
        int n = channel.write(src);
        if (n == 0) {
            throw new IOException("Blocking write không tiến triển");
        }
    }
}
~~~

This pattern assumes a **blocking and connected** channel. After a partial write, `src.position()` automatically advances to the next byte, so simply call `write(src)` again. **Do not `flip()` again**, and do not `clear()` while `src.hasRemaining()` is still true.

In non-blocking mode, instead of throwing immediately at `n == 0`, the application should keep the buffer in an outbound queue and register `OP_WRITE`. Only reuse or release a buffer once all of its bytes have been consumed.

### 6.1. OP_WRITE and backpressure

If an application keeps `OP_WRITE` enabled even when no data is waiting, the selector may report the socket writable very frequently, burning CPU. Common rules:

1. When there is data to send, enqueue the buffer and enable `OP_WRITE` if it cannot all be written immediately.
2. When `OP_WRITE` fires, try writing the buffer at the head of the queue, keeping the remainder on partial writes.
3. Once all buffers have no `remaining` bytes and the queue is empty, **remove `OP_WRITE` from the interest set**, keeping only needed events such as `OP_READ`.

A successful `write()` only confirms the bytes were accepted by the sending channel per contract; it **does not confirm** the peer application has processed the message. If business-level confirmation is required, define an application-layer ACK/response.

## 7. Blocking and Non-blocking: Behavior Reference Table

| Operation | Blocking mode | Non-blocking mode |
| --- | --- | --- |
| `SocketChannel.connect(remote)` | Waits to finish; typically returns `true` or errors. | May return `false` when connection is pending. |
| `SocketChannel.finishConnect()` | If pending, may wait until complete/error. | Returns `false` if still pending; use `OP_CONNECT` to wait. |
| `ServerSocketChannel.accept()` | May wait for a client to arrive. | Returns `null` if no connection is ready yet. |
| `SocketChannel.read(dst)` | May wait for at least one byte/EOF/error; does not guarantee filling buffer. | May return `0` if no bytes are ready yet. |
| `SocketChannel.write(src)` | May wait to make write progress; does not guarantee finishing buffer in one call. | May return `0` if temporarily unable to write. |

`configureBlocking(false)` must be called **before** registering the channel with a selector. If a channel is already registered with a selector and that registration is still active, switching back to blocking can throw `IllegalBlockingModeException`. To switch back to blocking, you must cancel the registration, ensure the key is no longer validly registered, and only then change the mode. Many designs keep non-blocking mode for the entire connection lifecycle to avoid this complexity.

Never build a `while` loop that immediately retries `finishConnect/accept/read/write` on every `false/null/0` without a wait condition or bounded iteration limit. It can turn into a busy-spin, spiking CPU and degrading throughput for other connections.

## 8. Runnable Java 17+ Example: TCP Loopback with connect, accept, read, and write

This example uses **blocking mode** to present the complete connection flow in a way that is easy to compile and verify. A server thread accepts a connection from `ServerSocketChannel.accept()`, reads the exact 4 bytes `PING`, and replies with the 2 bytes `OK`. The main thread acts as the client, connects over loopback, sends PING, and reads the response.

`finishConnect()` does not need to be called in the blocking example because `connect()` completes before returning successfully. The next section provides a dedicated non-blocking `finishConnect` example.

Save file `NioTcpLifecycleDemo.java`:

~~~java
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

public class NioTcpLifecycleDemo {

    static void readFully(SocketChannel channel, ByteBuffer dst)
            throws IOException {
        while (dst.hasRemaining()) {
            int n = channel.read(dst);
            if (n == -1) {
                throw new EOFException("Peer đóng khi dữ liệu chưa đủ");
            }
            if (n == 0) {
                throw new IOException("Blocking read không tiến triển");
            }
        }
    }

    static void writeFully(SocketChannel channel, ByteBuffer src)
            throws IOException {
        while (src.hasRemaining()) {
            int n = channel.write(src);
            if (n == 0) {
                throw new IOException("Blocking write không tiến triển");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> received = executor.submit(() -> {
                    try (SocketChannel peer = server.accept()) {
                        ByteBuffer incoming = ByteBuffer.allocate(4);
                        readFully(peer, incoming);
                        incoming.flip();

                        String request = StandardCharsets.US_ASCII
                                .decode(incoming).toString();

                        ByteBuffer reply = ByteBuffer.wrap(
                                "OK".getBytes(StandardCharsets.US_ASCII));
                        writeFully(peer, reply);
                        return request;
                    }
                });

                try (SocketChannel client = SocketChannel.open()) {
                    boolean connected = client.connect(
                            (InetSocketAddress) server.getLocalAddress());

                    ByteBuffer request = ByteBuffer.wrap(
                            "PING".getBytes(StandardCharsets.US_ASCII));
                    writeFully(client, request);

                    ByteBuffer answer = ByteBuffer.allocate(2);
                    readFully(client, answer);
                    answer.flip();

                    String acknowledgment = StandardCharsets.US_ASCII
                            .decode(answer).toString();

                    System.out.println("connected=" + connected);
                    System.out.println("response=" + acknowledgment);
                }

                System.out.println("received=" +
                        received.get(5, TimeUnit.SECONDS));
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac NioTcpLifecycleDemo.java
java NioTcpLifecycleDemo
~~~

**Stdout in an environment allowing loopback TCP connections:**

~~~text
connected=true
response=OK
received=PING
~~~

Mapping to the APIs:

1. `server.bind(...)` listens on an OS-chosen loopback port. The client uses `server.getLocalAddress()` so no hardcoded port is required.
2. `server.accept()` on the worker thread waits for a connection and returns `SocketChannel peer`. Because accepted sockets default to blocking, the `readFully` loop fits cleanly.
3. `client.connect(...)` in blocking mode returns `true` when the connection succeeds.
4. `client.write(...)` sends the 4 bytes of PING; `writeFully` loops if necessary until the buffer is exhausted.
5. `peer.read(...)` receives all 4 bytes via `readFully` and calls `flip()` to decode ASCII.
6. The server writes back 2 bytes of OK; the client reads them all, calls `flip()`, and decodes.
7. Only the main thread prints to stdout, so output line order is deterministic. `Future.get` retrieves the server's result once processing finishes.

This example runs over real local TCP, so the environment must allow opening loopback sockets. It does not use a selector and does not artificially force partial reads/writes; `readFully`/`writeFully` are written strictly to contract even if a transfer moves fewer bytes than requested. In production applications, add deadlines/timeouts for the overall read/write lifecycle, size limits, and shutdown mechanisms if a peer becomes unresponsive.

## 9. Simple Non-blocking connect/finishConnect Example

Once you understand the blocking cycle, you can switch the client side alone to non-blocking. This snippet illustrates **connection establishment**, not a complete production server:

~~~java
try (SocketChannel client = SocketChannel.open();
     Selector selector = Selector.open()) {

    client.configureBlocking(false);
    boolean connected = client.connect(remote);

    if (!connected) {
        SelectionKey key = client.register(
                selector, SelectionKey.OP_CONNECT);

        while (!client.finishConnect()) {
            int ready = selector.select(5_000);
            if (ready == 0) {
                throw new java.net.SocketTimeoutException(
                        "Kết nối không sẵn sàng");
            }
            selector.selectedKeys().clear();
        }
        key.cancel();
    }

    // client.isConnected() == true:
    // Can now register read/write or perform non-blocking send/receive.
}
~~~

This is an **illustrative snippet** assuming `remote` is a provided `SocketAddress` and importing `java.nio.channels.SocketChannel`, `Selector`, `SelectionKey`, `java.net.SocketAddress`. For a multi-connection event loop, manage state using each `SelectionKey` and its attachment rather than a dedicated connect loop like above.

If you call `client.read(...)` or `client.write(...)` right after `connect(remote)` returns `false` without completing `finishConnect()`, `NotYetConnectedException` may be thrown. Thus `OP_CONNECT` and the `finishConnect` step must be completed before `OP_READ/OP_WRITE`.

### 9.1. SelectionKey Handling Skeleton

~~~java
Iterator<SelectionKey> it = selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();

    if (!key.isValid()) {
        continue;
    }
    try {
        if (key.isAcceptable()) {
            // ServerSocketChannel.accept() in non-blocking mode.
        }
        if (key.isConnectable()) {
            // SocketChannel.finishConnect() for pending connect.
        }
        if (key.isReadable()) {
            // SocketChannel.read(...); handle >0, 0, -1.
        }
        if (key.isWritable()) {
            // SocketChannel.write(...); handle partial/0.
        }
    } catch (IOException ex) {
        key.cancel();
        key.channel().close();
    }
}
~~~

This is **event-loop skeleton pseudocode**: `selector` and the channels must be initialized, registered in the right mode, and must manage `ByteBuffer` instances and connection state. The branches are not production code yet. You cannot just read once in `isReadable` and assume an entire message has arrived.

## 10. Edge Cases That Easily Cause Bugs

### 10.1. connect returns false and finishConnect is skipped

~~~java
client.configureBlocking(false);
boolean done = client.connect(remote);
// Wrong if done == false and client.write(...) is called immediately.
~~~

Correct approach: when pending, register `OP_CONNECT` and call `finishConnect()` until it succeeds or errors/times out. `isConnected()` helps monitor state but does not replace the completion contract of `finishConnect()`.

### 10.2. accept returns null and the server is assumed broken

In non-blocking mode, `accept() == null` is a normal result when no connection is waiting. Wait for `OP_ACCEPT` instead of spinning indefinitely.

### 10.3. read returning 0 is mistaken for EOF

`0` means no bytes were transferred on that call; `-1` indicates the read direction has reached end-of-stream. In non-blocking mode, wait for `OP_READ`. With a blocking channel and buffer space available, `0` signals a need to review assumptions about the provider or application state.

### 10.4. Calling read() once and parsing an entire frame

The buffer might not hold a complete frame yet. Check `n` and `remaining()`, preserve parser state across reads, and handle the case where one read contains multiple frames. Use `compact()` when trailing bytes form an incomplete frame.

### 10.5. Calling clear() on the buffer immediately after write()

If write only sent part of the data, `clear()` can allow unsent bytes to be overwritten. Preserve the current `position/limit`; continue sending when the channel is ready.

### 10.6. Registering OP_WRITE continuously

Sockets are very often "ready to write", even when the application has nothing to send. Keeping `OP_WRITE` enabled throughout the connection lifetime can wake the selector excessively; enable it only when bytes are actually queued to write, and turn it off when the queue is empty.

### 10.7. Calling configureBlocking(true) while still registered with a selector

If the channel still holds a valid registration, switching to blocking mode can throw `IllegalBlockingModeException`. Structure the channel lifecycle so mode and selector registration stay consistent.

### 10.8. Ignoring half-close from the peer

When `read() == -1`, the peer has closed its sending side; the application may still have pending outbound bytes in the reverse direction depending on the protocol. Choose a clean shutdown flow to flush required outbound data or abort according to clear rules. Never treat EOF as "the socket has been destroyed in both directions" by default.

### 10.9. Believing completed write means the peer processed the data

Flushing a buffer only says the data was handed off to the sender's channel mechanism per contract. TCP and the receiver's application logic are separate layers. If business-level confirmation is required, the protocol needs an explicit reply/ACK message.

### 10.10. Not bounding connection resources

Each client may hold a socket, buffers, and parser state. A production server must limit connection counts, frame sizes, header/payload wait times, write queues, receive rates, and close/cancel mechanisms to prevent exhausting memory and file descriptors.

## 11. Decision Table Summary

| What are you doing? | Appropriate API | Signal to continue/handle |
| --- | --- | --- |
| Client initiates connection | `SocketChannel.connect(remote)` | `false` in non-blocking → currently pending. |
| Client has pending connection | `SocketChannel.finishConnect()` | `false` → wait for OP_CONNECT; `true` → connected. |
| Server accepts client | `ServerSocketChannel.accept()` | `null` in non-blocking → wait for OP_ACCEPT. |
| Read payload into buffer | `SocketChannel.read(dst)` | `>0` process bytes; `0` wait more; `-1` EOF. |
| Write buffer to TCP | `SocketChannel.write(src)` | `>0` check remaining; `0` wait for OP_WRITE. |
| Read multi-chunk messages | `ByteBuffer.flip/compact` + parser | Keep partial-frame bytes; do not clear prematurely. |
| Wait for readiness on many channels | `Selector.select` + `SelectionKey` | Handle kind, mode, timeout, and lifecycle properly. |

## 12. Self-Check Exercises

1. **Which method accepts a TCP connection on the server?** `ServerSocketChannel.accept()`, returning the new client's `SocketChannel`.
2. **Does non-blocking `connect(remote)` returning `false` mean failure?** No. The connection is pending; `finishConnect()` is required.
3. **What does `finishConnect()` returning `false` mean?** Not yet complete; wait for readiness or use an appropriate retry mechanism.
4. **Which event is typically associated with a pending client connection?** `SelectionKey.OP_CONNECT`.
5. **What does non-blocking `accept()` return when no connection is waiting?** `null`.
6. **Does a SocketChannel returned by server accept automatically inherit non-blocking mode from the listener?** No. Accepted channels start in blocking mode; configure it explicitly if using a selector.
7. **Is `read(buffer)` returning `0` an EOF?** No; `-1` signals EOF on the read side.
8. **If `write(buffer)` sent 3 of 8 bytes, where does the next send continue from?** From the current `buffer.position()`, without calling flip/clear again; 5 bytes remain.
9. **Do two client calls `client.write("HE")` and `client.write("LLO")` guarantee two matching `server.read` calls?** No, TCP is a byte stream.
10. **Why must `OP_WRITE` be disabled when no outbound data remains?** So the event loop avoids repeated writable notifications.
11. **Does a successful connect mean the server side has already sent a full frame?** No. Connection lifecycle and message framing are independent.
12. **Can a socket that received `-1` from read still have data to send?** Possibly, under half-close protocols; decide how to handle it based on application state.

**Remember:** `connect` initiates TCP setup, `finishConnect` confirms completion of a pending connection, `accept` creates the server-side client socket, and `read/write` transfer portions of a **byte stream**. With non-blocking NIO, inspect **return values, buffer state, and readiness events**, preserve unprocessed bytes, and implement clear close/timeout mechanisms.
