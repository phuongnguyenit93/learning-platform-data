# SocketChannel, ServerSocketChannel, and the Default Blocking Mode (Java 17+)

In Java NIO, `ServerSocketChannel` represents the listening endpoint for TCP connections, while `SocketChannel` represents an established or connecting TCP connection. Despite the *NIO* name, **both newly created channels are in blocking mode by default**. NIO does not mean "every I/O call is asynchronous," nor does it mean you must use a `Selector` from the start.

This foundational topic belongs to the **Buffers and Channels** group: channels read and write through `ByteBuffer`, not directly through `byte[]` as in many classic `Socket.getInputStream()` examples. This article helps you understand the channel lifecycle, the blocking semantics of `open/connect/bind/accept/read/write`, `ByteBuffer` rules, how to run a simple TCP server using blocking NIO, and when to switch to non-blocking + `Selector`.

## 1. The Big Picture: Two Channel Types, Two Roles

```text
Client JVM                                  Server JVM
-----------------                           ------------------
SocketChannel.open(...)                     ServerSocketChannel.open()
connect(serverAddress)                      bind(listenAddress)
       |                                          |
       | ------------ TCP connect --------------> |
       |                                          | accept()
       |                                          v
       |                                    SocketChannel peer
       |                                          |
write(ByteBuffer) -----------------------> read(ByteBuffer)
read(ByteBuffer)  <----------------------- write(ByteBuffer)
       |                                          |
  close() / half-close                    close() / half-close
```

- **`ServerSocketChannel`**: the object listening on an address/port; it does not directly `read/write` application data for clients. Each accepted connection creates a **separate `SocketChannel`**.
- **`SocketChannel`**: a full-duplex channel for a TCP connection; reads/writes bytes via `ByteBuffer`. A client endpoint can be created with `SocketChannel.open(address)` or `open()` followed by `connect(address)`.
- **`ByteBuffer`**: stores a byte region with `position`, `limit`, and `capacity`, used to transfer bytes between a channel and the application.
- **`SelectableChannel`**: the base class for both channel types; you can call `configureBlocking(false)` to register it with a `Selector` when you want to handle readiness across multiple sockets.

A typical blocking server uses **one accept thread** and hands off each client to an appropriate thread/task. Do not mix *connection listening* logic with *reading requests from an accepted connection* logic.

## 2. Default Blocking: Which Object Exactly Defaults to Blocking?

Immediately after creation using the standard factory APIs:

| Object / Operation | State / Basic Behavior |
| --- | --- |
| `ServerSocketChannel.open()` | Channel is **open, unbound**, default **blocking=true** |
| `server.bind(localAddress)` | Binds address/port; **does not** turn the channel into non-blocking |
| `server.accept()` when blocking=true | Waits for an incoming connection, or error/close/interrupt; returns a `SocketChannel` |
| `SocketChannel.open()` | Channel is **open, unconnected**, default **blocking=true** |
| `SocketChannel.open(remote)` | Creates the channel and connects to remote in default blocking mode; if successful, returns a connected channel |
| `channel.connect(remote)` when blocking=true | Waits for the connection to complete or an error to occur |
| `server.accept()` when server is non-blocking | If no connection is pending, returns `null` immediately |
| `SocketChannel` returned by `accept()` | **Always in blocking mode when first returned**, even if the listening channel is non-blocking |

**Most common point of confusion:** `ServerSocketChannel.configureBlocking(false)` only changes **the mode of that listening channel**. It **does not automatically** turn accepted `SocketChannel` instances into non-blocking channels. To register an accepted socket with a `Selector`, you must explicitly call `accepted.configureBlocking(false)`.

You can check the state with `isBlocking()`, but that result only reflects the channel's mode configuration; it **does not prove the peer is alive**, does not confirm that a full request's bytes have arrived, and does not guarantee that a single read call will fill the buffer.

## 3. Creating and Binding ServerSocketChannel with the Proper Lifecycle

For an internet TCP socket, a minimal sequence:

```java
// Illustrative snippet inside a method that throws IOException.
try (ServerSocketChannel server = ServerSocketChannel.open()) {
    server.bind(new InetSocketAddress("127.0.0.1", 8080));
    while (true) {
        SocketChannel client = server.accept(); // blocking by default
        // Hand off client to an owner handler that closes it when finished.
    }
}
```

This snippet **only illustrates the lifecycle**—it has no handler closing `client` and no shutdown strategy: do not deploy it as-is in production. Things to keep in mind:

1. `open()` creates an **unbound** channel. Calling `accept()` before `bind(...)` on an internet socket can throw `NotYetBoundException`, rather than silently opening a random port.
2. `bind(new InetSocketAddress(address, 0))` uses **port 0** so the operating system assigns a free port, which is very convenient for testing. Use `getLocalAddress()` to read the port after binding.
3. `bind(...)` can fail (port in use, address does not exist, permission denied, OS limits). Do not ignore `IOException`.
4. `accept()` in blocking mode waits until a connection is pending or a cancellation/error event occurs; it is **not** a "poll and return null" call as in non-blocking mode.
5. For a public server, determine which wildcard/interface to bind to and what TLS/authentication/network firewall mechanisms to use. Bind to loopback for testing; do not expose to the Internet in learning examples.
6. Each accepted connection needs an owner responsible for closing the `SocketChannel` when finished. Closing an accepted channel **does not** automatically close the listening channel.
7. The pending connection queue (**backlog**) and operating system limits do not mean an unlimited number of clients can be handled. Design handler limits and overload behavior.

Multiple threads can call `accept()` on a single `ServerSocketChannel`, and the Java API synchronizes concurrent accepts at the channel level. Having multiple threads call accept does not replace lifecycle/dispatch design.

## 4. Connecting a Client with SocketChannel: Blocking Connect

Two common approaches:

```java
// Approach A: open then connect
try (SocketChannel channel = SocketChannel.open()) {
    boolean connected =
            channel.connect(new InetSocketAddress("127.0.0.1", 8080));
    // In blocking mode, a successful connect -> connected == true.
}

// Approach B: factory creates and connects directly
try (SocketChannel channel = SocketChannel.open(
        new InetSocketAddress("127.0.0.1", 8080))) {
    // Already connected if the constructor/factory returns normally.
}
```

Both snippets are **API illustrations** and only run if a server is actually listening on port 8080. In blocking mode, `connect(remote)` waits for the connection to complete or report an error; on success, it normally returns `true`. In non-blocking mode, it may return `false`, meaning the connection process is **in progress**, and you need to handle `finishConnect()` when the socket is ready, typically after a `Selector` `OP_CONNECT` event.

`isConnected()` reflects the established connection state of the channel; it is not a health check for all future operations. The connection may be closed or fail immediately after the check. Do not call `read/write` before the connection is complete: the APIs may throw `NotYetConnectedException`.

**Timeout:** a blocking `connect` may wait for a long time depending on the network/OS. Java NIO's `SocketChannel.connect` does not take a timeout parameter like `Socket.connect(endpoint, timeout)`. When a strict connection deadline is needed, you must design an appropriate timeout management mechanism (such as non-blocking connect + Selector + deadline, or using another API/protocol). Do not assume that configuring a socket read timeout will automatically become the channel's connect timeout.

## 5. How Blocking Mode Affects accept/read/write

| API | Blocking mode (`true`) | Non-blocking mode (`false`) |
| --- | --- | --- |
| `ServerSocketChannel.accept()` | Waits for a connection; returns a channel when available | May return `null` immediately if no pending connection exists |
| `SocketChannel.connect(addr)` | Waits for success/error | May return `false`; completes via `finishConnect()` |
| `SocketChannel.read(dst)` | With `dst.remaining()>0`, waits for **at least 1 byte**, EOF, or error; does not promise to fill the buffer | May return `0` when no bytes are available yet |
| `SocketChannel.write(src)` | Normally waits to write all requested bytes into the channel's send path or errors; may block when the send buffer is full | May write partially or `0` when there is no space at that moment |
| `Selector.register(...)` | **Cannot** register a channel while it is still blocking | Required mode to register a selectable channel with a selector |

In blocking mode, **`read` returning fewer bytes than `dst.remaining()` is valid**. For example, if the buffer has 4096 bytes of space remaining but the peer has only sent 10 bytes so far, `read` may return 10. It does not necessarily wait for all 4096 bytes.

In blocking `SocketChannel.write(src)`, the channel contract normally attempts to write all of `src.remaining()` before returning. Even so, a `while (src.hasRemaining())` loop remains a safe idiom to consistently track `ByteBuffer.position()` and avoid relying on assumptions if the design changes to non-blocking or gathering writes. **Finishing a write does not mean the peer application has finished processing it.**

If reading cannot proceed because the peer has orderly closed its sending side and no data remains, `read` returns **`-1`** (EOF). If the buffer is empty (`remaining()==0`), `read` may return `0` without requiring data on the connection.

## 6. ByteBuffer: position, limit, capacity, and Switching Between Read/Write

A `ByteBuffer` has three essential numbers:

- **`capacity`**: the fixed capacity of the buffer.
- **`limit`**: the upper bound (exclusive) of the data/memory currently accessible in the current mode.
- **`position`**: the index of the next byte to put or get.

Always `0 <= position <= limit <= capacity`. Example with `ByteBuffer.allocate(8)`:

```text
Newly allocated:  position=0, limit=8, capacity=8
put 3 bytes:      position=3, limit=8, capacity=8
flip():           position=0, limit=3, capacity=8   (read 3 bytes)
get 2 bytes:      position=2, limit=3, capacity=8
compact():        position=1, limit=8, capacity=8   (keep 1 remaining byte)
flip():           position=0, limit=1, capacity=8   (read the remaining byte)
```

When **receiving over TCP**, the channel writes bytes from the socket into the buffer (`channel.read(buffer)`). The application then switches the buffer from **write mode → read mode** using `flip()`, consumes valid bytes, and calls `clear()` if everything was processed or `compact()` if unconsumed bytes remain.

When **sending over TCP**, the application writes bytes into the buffer (or uses `ByteBuffer.wrap(payload)`/`StandardCharsets.UTF_8.encode(text)`), calls `flip()` if it just called `put(...)`, and then calls `channel.write(buffer)` so the channel consumes bytes from `position` to `limit`.

| Method | What does it do? | What does it NOT do? |
| --- | --- | --- |
| `flip()` | `limit = position; position = 0`, prepares to **read bytes just written** | Does not copy data |
| `clear()` | `position = 0; limit = capacity`, prepares to **overwrite** the buffer | **Does not** zero out old bytes |
| `compact()` | Keeps unconsumed bytes, shifts them to the front, and prepares to receive more | Does not retain already consumed bytes |
| `rewind()` | `position = 0`, re-reads within the current `limit` | Does not change `limit` |
| `remaining()` | `limit - position` | Not the number of TCP bytes remaining on the network |
| `hasRemaining()` | Indicates whether bytes remain in the defined buffer region | Does not mean "the socket is still open" |

A very common bug is calling `read(buffer)` and **forgetting `flip()`**, then parsing the region from `position` to `limit`. In that case, the parser may skip the newly received bytes or read stale old data.

## 7. Multi-Read Loops: TCP Is a Byte Stream, Not Message Boundaries

Suppose the client calls `write` twice with two strings `ABC` and `DEF`. The server might receive `AB`, `CDE`, `F` across three `read` calls, or `ABCDEF` in a single `read`. TCP only preserves **byte order**, not the boundaries of `write` calls.

A loop receiving bytes until EOF (illustrative snippet, **not a standalone program**, assuming `channel` is already connected):

```java
ByteBuffer buffer = ByteBuffer.allocate(1024);
while (true) {
    int n = channel.read(buffer); // May block.
    if (n == -1) break;           // Peer closed its send side.
    buffer.flip();
    while (buffer.hasRemaining()) {
        byte oneByte = buffer.get();
        // Process available byte; not necessarily a full message yet.
    }
    buffer.clear();
}
```

This snippet is suitable when the application intentionally **reads until EOF** and the received data fits within budget. However, for a protocol that keeps the socket open to send multiple requests/responses, **EOF is not the boundary of each message**; reading until EOF can cause deadlock when both sides keep the connection open waiting for each other.

**Do not decode UTF-8 on each `ByteBuffer` read independently** when multi-byte characters could be split across read calls. Either assemble the exact bytes of each frame first and decode once, or use a stateful decoder across chunks. Do not treat `available()` on a stream/socket wrapper as the byte count of the incoming message.

## 8. Complete Example 1 — BlockingChannelEcho: accept, read, write, half-close

The file **`BlockingChannelEcho.java`** creates a listener on IPv4 loopback `127.0.0.1` with an ephemeral port, opens a client `SocketChannel`, accepts it into a server-side `SocketChannel`, and exchanges a request/response.

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;

public class BlockingChannelEcho {
    private static void writeAll(SocketChannel channel, String message)
            throws IOException {
        ByteBuffer src = StandardCharsets.UTF_8.encode(message);
        while (src.hasRemaining()) {
            channel.write(src);
        }
    }

    private static String readToEof(SocketChannel channel)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        ByteBuffer buffer = ByteBuffer.allocate(3);
        while (true) {
            int n = channel.read(buffer);
            if (n == -1) {
                break;
            }
            buffer.flip();
            while (buffer.hasRemaining()) {
                bytes.write(buffer.get() & 0xFF);
            }
            buffer.clear();
        }
        return new String(bytes.toByteArray(), StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        InetAddress local =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(local, 0));
            int port = ((InetSocketAddress) listener.getLocalAddress())
                    .getPort();

            try (SocketChannel client = SocketChannel.open(
                         new InetSocketAddress(local, port));
                 SocketChannel accepted = listener.accept()) {

                System.out.println("Listener blocking: "
                        + listener.isBlocking());
                System.out.println("Client blocking: "
                        + client.isBlocking());
                System.out.println("Accepted blocking: "
                        + accepted.isBlocking());

                writeAll(client, "HELLO NIO");
                client.shutdownOutput();

                String request = readToEof(accepted);
                writeAll(accepted, "ACK " + request);
                accepted.shutdownOutput();

                String response = readToEof(client);
                System.out.println("Server saw: " + request);
                System.out.println("Client saw: " + response);
            }
        }
    }
}
```

Compile and run with JDK 17+:

```sh
javac -encoding UTF-8 BlockingChannelEcho.java
java BlockingChannelEcho
```

Deterministic stdout on a successful run:

```text
Listener blocking: true
Client blocking: true
Accepted blocking: true
Server saw: HELLO NIO
Client saw: ACK HELLO NIO
```

Key points in the code:

1. `ServerSocketChannel.open()` is blocking by default, but **unbound**; `bind(new InetSocketAddress(local, 0))` creates the listening endpoint.
2. `SocketChannel.open(remote)` connects in blocking mode. `listener.accept()` returns a separate connected channel for the server side, also blocking by default.
3. `StandardCharsets.UTF_8.encode(message)` already creates a `ByteBuffer` ready to be read for writing to the channel, so **do not call `flip()` again** on that buffer.
4. `readToEof` intentionally uses a small **3-byte** buffer to observe multi-read behavior; it only accumulates bytes and does not decode per chunk. Only after all bytes in one direction are assembled does it construct the `String`.
5. `client.shutdownOutput()` signals that the client will send no more requests. The server reads until EOF, yet **can still write the response in the reverse direction** because TCP connections are full-duplex.
6. `accepted.shutdownOutput()` signals the end of the response. The client also reads until EOF, then checks the complete string.

The program uses **a single thread** because the write/half-close/read order is arranged so there is no circular wait. For interactive applications with multiple messages, you must switch to framing rather than relying on `shutdownOutput` after each message. Success on loopback does not prove a production server handles overload, out-of-order closes, or WAN disconnects.

## 9. Framing with SocketChannel: Application-Level readFully

To send multiple messages over the same TCP connection, design a **length-prefix**. For example, each message uses a 4-byte big-endian header describing the number of UTF-8 bytes that follow:

```text
+----------------------------+------------------------+
| 4-byte int N (big-endian)  | N byte UTF-8 payload    |
+----------------------------+------------------------+

sender: putInt(N) -> flip() -> writeFully(header)
        wrap(payload) -> writeFully(body)

receiver: readFully(4-byte header) -> flip() -> getInt()
          validate N -> readFully(N-byte body) -> flip() -> decode once
```

The **`readFully` loop** is an **application-protocol** utility, not a built-in API on `SocketChannel`:

```java
// Illustrative snippet: ch and dst already exist, blocking mode.
while (dst.hasRemaining()) {
    int n = ch.read(dst);
    if (n == -1) {
        throw new EOFException("Frame ended early");
    }
}
```

On a blocking `SocketChannel` when `dst.remaining() > 0`, `read` waits for bytes/EOF/error; the loop therefore completes when the declared number of bytes is received or fails on early EOF. **Do not copy this loop as-is into non-blocking mode**: `read` can return `0`, causing the loop to spin CPU with no progress. In non-blocking mode, you must retain partial state and wait for a new `OP_READ` (or appropriate readiness).

If the peer declares an excessively large or negative `N`, reject it **before allocating** the body buffer; enforce limits per protocol, tenant, and real memory. If the frame is incomplete when the peer closes the connection, throw `EOFException` and do not pass partial data into business logic.

## 10. Complete Example 2 — FramedBlockingNio: Two Frames on One Connection

The file **`FramedBlockingNio.java`** uses `ByteBuffer` to write/read a big-endian `int32` header, caps each payload at **4,096 bytes**, sends two UTF-8 frames, and receives a reply frame on the **same** TCP socket. The receiver uses `CharsetDecoder` in `REPORT` mode so invalid UTF-8 bytes are not silently replaced.

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class FramedBlockingNio {
    private static final int MAX_PAYLOAD = 4096;

    private static void writeFully(SocketChannel channel, ByteBuffer data)
            throws IOException {
        while (data.hasRemaining()) {
            channel.write(data);
        }
    }

    private static void readFully(SocketChannel channel, ByteBuffer target)
            throws IOException {
        while (target.hasRemaining()) {
            if (channel.read(target) == -1) {
                throw new EOFException("Incomplete frame");
            }
        }
    }

    private static void sendFrame(SocketChannel channel, String text)
            throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        if (payload.length > MAX_PAYLOAD) {
            throw new IOException("Frame too large");
        }
        ByteBuffer header = ByteBuffer.allocate(4)
                .order(ByteOrder.BIG_ENDIAN);
        header.putInt(payload.length);
        header.flip();
        writeFully(channel, header);
        writeFully(channel, ByteBuffer.wrap(payload));
    }

    private static String receiveFrame(SocketChannel channel)
            throws IOException {
        ByteBuffer header = ByteBuffer.allocate(4)
                .order(ByteOrder.BIG_ENDIAN);
        readFully(channel, header);
        header.flip();

        int length = header.getInt();
        if (length < 0 || length > MAX_PAYLOAD) {
            throw new IOException("Invalid length: " + length);
        }

        ByteBuffer body = ByteBuffer.allocate(length);
        readFully(channel, body);
        body.flip();
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(body).toString();
    }

    public static void main(String[] args) throws Exception {
        InetAddress local =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
        String first = "Xin chào";
        String second = "NIO \uD83D\uDE00";

        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(local, 0));
            int port = ((InetSocketAddress) listener.getLocalAddress())
                    .getPort();

            try (SocketChannel client = SocketChannel.open(
                         new InetSocketAddress(local, port));
                 SocketChannel accepted = listener.accept()) {

                sendFrame(client, first);
                sendFrame(client, second);

                String one = receiveFrame(accepted);
                String two = receiveFrame(accepted);
                sendFrame(accepted, "OK 2");

                String reply = receiveFrame(client);
                System.out.println("Frames received: 2");
                System.out.println("First matches: "
                        + first.equals(one));
                System.out.println("Second matches: "
                        + second.equals(two));
                System.out.println("First UTF-8 bytes: "
                        + first.getBytes(StandardCharsets.UTF_8).length);
                System.out.println("Reply: " + reply);
            }
        }
    }
}
```

Run:

```sh
javac -encoding UTF-8 FramedBlockingNio.java
java FramedBlockingNio
```

Deterministic stdout:

```text
Frames received: 2
First matches: true
Second matches: true
First UTF-8 bytes: 9
Reply: OK 2
```

Explanation:

- `"Xin chào"` has **9 UTF-8 bytes**; the frame length must be `payload.length`, not `String.length()`. The second string contains a non-BMP emoji to test Unicode handling across a byte stream.
- `ByteBuffer.allocate(4).order(ByteOrder.BIG_ENDIAN)` writes and reads the int consistently; `putInt` advances `position`, so the sender calls `flip` before writing.
- `readFully(header)` does not assume a single read receives all 4 bytes. `readFully(body)` does not assume a read aligns with a single frame send. `body.flip()` prepares the decoder to consume the exact N bytes.
- `while (data.hasRemaining()) channel.write(data)` tracks the unwritten portion of the buffer; useful when extending the code, though when switching to non-blocking you **must handle `0` via readiness**, never spin.
- Both frames are reassembled accurately thanks to the **length header**, without depending on EOF. After the server reads both frames, it sends the `OK 2` reply frame; the client reads the single reply frame without waiting for the server to close the connection.
- `newDecoder().onMalformedInput(REPORT)` reports an error on invalid UTF-8 bytes; `String.getBytes(UTF_8)` normally replaces invalid surrogates on the source side, so if Java input data can be malformed, validation/strict encoding is also needed on the sending side.

This is a **small-volume synchronous blocking** demo, not representative of an event-loop design. To protect production systems, add end-to-end deadlines, queue bounds, peer authentication, a policy for malformed messages, and connection closure on protocol errors.

## 11. Switching to Non-Blocking: configureBlocking(false) Is Not a "Faster Read" Call

`SelectableChannel.configureBlocking(false)` changes how operations wait:

```java
// Illustrative, not a standalone class.
server.configureBlocking(false);
SocketChannel incoming = server.accept();
if (incoming == null) {
    // No pending connection yet: this is a normal result.
}

// After a successful accept:
incoming.configureBlocking(false); // Change the accepted channel separately.
```

In non-blocking mode:

- `accept()` may return `null`; that is neither EOF nor an error.
- `connect()` may not finish immediately; when `false`, track the state and call `finishConnect()` at the right time.
- `read(ByteBuffer)` may return `0` if no bytes are immediately available; you must retain the `ByteBuffer` and parser state to continue on a later event.
- `write(ByteBuffer)` may write **partially** or `0`; you must retain the unwritten remainder to retry when writable. **`OP_WRITE` is usually always "ready" when the socket has buffer space**, so only register interest in `OP_WRITE` when there is actually pending outbound data to avoid a busy loop.
- An accepted `SocketChannel` **is still `blocking=true`** when `accept()` returns, even if the listening channel is non-blocking; you must change the accepted channel's mode if you want to register it with a selector.

**Do not** use continuous `while (channel.read(buffer) == 0) { }` or `while (channel.write(buffer) == 0) { }` loops in non-blocking code: they only burn CPU. Use readiness notifications/`Selector` and manage backpressure.

## 12. Complete Example 3 — BlockingModeSwitch: Mode and accept(null)

The file **`BlockingModeSwitch.java`** shows that the same `ServerSocketChannel` can switch to non-blocking when not registered with a selector, receive `null` while no client is waiting, and then switch back to blocking. The client is opened **after** the non-blocking `accept` call so the "no pending client" state is deterministic.

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;

public class BlockingModeSwitch {
    public static void main(String[] args) throws Exception {
        InetAddress local =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(local, 0));
            int port = ((InetSocketAddress) listener.getLocalAddress())
                    .getPort();

            System.out.println("Default blocking: "
                    + listener.isBlocking());
            listener.configureBlocking(false);
            System.out.println("Nonblocking now: "
                    + !listener.isBlocking());

            // No client has been created: accept returns null immediately.
            SocketChannel absent = listener.accept();
            System.out.println("No pending client: " + (absent == null));

            listener.configureBlocking(true);
            try (SocketChannel client = SocketChannel.open(
                         new InetSocketAddress(local, port));
                 SocketChannel accepted = listener.accept()) {
                System.out.println("Blocking restored: "
                        + listener.isBlocking());
                System.out.println("Accepted blocking: "
                        + accepted.isBlocking());
                System.out.println("Client connected: "
                        + client.isConnected());
            }
        }
    }
}
```

Run:

```sh
javac -encoding UTF-8 BlockingModeSwitch.java
java BlockingModeSwitch
```

Stdout:

```text
Default blocking: true
Nonblocking now: true
No pending client: true
Blocking restored: true
Accepted blocking: true
Client connected: true
```

In this program, `listener.configureBlocking(true)` is safe because it **was never registered with a `Selector`**. If a channel has a valid registration/key in a selector, attempting to re-enable blocking mode throws `IllegalBlockingModeException`; you must cancel the key and wait for the registration to become invalid according to the proper lifecycle before changing mode.

This example only demonstrates mode switching. It **does not** build an event loop; a real server does not repeatedly flip between blocking↔non-blocking to "check if data is available," but instead chooses an appropriate concurrency model.

## 13. A Brief Introduction to Selector, Just Enough to Understand Blocking

A `Selector` lets **one thread monitor readiness** of multiple selectable channels already in non-blocking mode. Operations are typically associated with `SelectionKey`:

| Channel | Commonly used supported ops | When to express interest |
| --- | --- | --- |
| `ServerSocketChannel` | `OP_ACCEPT` | Ready to accept a new connection |
| `SocketChannel` with pending connect | `OP_CONNECT` | Ready to complete `finishConnect()` |
| Connected `SocketChannel` | `OP_READ` | Ready to read; may also encounter EOF |
| `SocketChannel` with pending outbound bytes | `OP_WRITE` | Ready to write more, though does not promise to write the whole buffer |

Basic sequence:

```text
server.configureBlocking(false)
server.register(selector, OP_ACCEPT)
                 |
              select()
                 |
               ready
                 |
           server.accept()
                 |
       accepted.configureBlocking(false)
       accepted.register(selector, OP_READ)
                 |
         read into per-connection ByteBuffer
         parse complete frames; retain incomplete bytes
                 |
       queue response; when necessary enable OP_WRITE
                 |
          write until no progress
```

`Selector.select()` may block the **selector thread** while waiting for events; that **does not turn operations on the channels back into blocking mode**. Readiness does not promise that a full TCP request is available. Even when an `OP_READ` event fires, the code must handle the actual byte count received, `-1`, and incomplete frames.

Scaling from a blocking server to a selector is a change in **state-machine architecture and ownership**, not merely adding `configureBlocking(false)` to each socket. Do not try to register a newly accepted `SocketChannel` while forgetting to change its mode.

## 14. Errors, Timeouts, Interrupts, and Closing Blocking Channels

### Blocking I/O Can Wait a Long Time

- `server.accept()` can wait until a client arrives.
- `SocketChannel.read(buffer)` can wait for bytes/EOF; if the peer keeps the socket open without sending, the application can wait a very long time.
- `SocketChannel.write(buffer)` can wait when the peer reads slowly and the kernel send buffer fills up.
- `SocketChannel.connect(endpoint)` can wait for connection establishment; the deadline depends on the OS if you do not design your own timeout.

A blocking server program needs **protocol-level timeout/deadline** policies, resource limits, and safe shutdown paths. Do not assume `Socket.setSoTimeout` applies to every `SocketChannel.read` call: depending on the API, that option is tied to socket stream read operations, not a "universal timeout for all channel methods." For channels requiring strict deadlines, consider a non-blocking selector + deadline or a managed coordination/cancellation mechanism.

### How to Cancel a Blocked Thread

For standard channels implementing `InterruptibleChannel`:

- A thread blocked in `accept/read/write` can be **interrupted** by another thread: the channel is closed and typically throws `ClosedByInterruptException`; the interrupt status is set. **Do not reuse a closed channel**.
- Another thread **closing the channel** while I/O is blocked can result in `AsynchronousCloseException`; the caller must handle closing the session.
- An orderly close of the peer's send side causes `read` to eventually return `-1` **after previously sent bytes have been delivered to the application**. Connection resets/errors may throw `IOException` instead of returning EOF.
- `SocketChannel.shutdownOutput()` closes the **send direction** so the peer can observe EOF, while the receive direction of the same connection can still remain active. `close()` releases the entire channel and does not certify that the peer processed the payload.

Notable exceptions to recognize: `ClosedChannelException`, `NotYetConnectedException`, `NotYetBoundException`, `ConnectException`/`IOException`, `ClosedByInterruptException`, `AsynchronousCloseException`, and `IllegalBlockingModeException` when violating selector/blocking mode rules.

**Guarantee distinction:** a successful `SocketChannel.write` only certifies that the channel's write operation completed per its interface; it **does not prove** the peer application finished reading or committed the transaction. To confirm business-level completion, an application-level response/ACK is required.

## 15. Multi-Client Blocking Servers: Limits and Correctness

A blocking accept loop does not necessarily block **all connections**, provided handlers are separated:

```text
Listener thread (blocking accept)
   |
   +--> client A --> worker A: blocking read/parse/write
   +--> client B --> worker B: blocking read/parse/write
   +--> client C --> worker C: blocking read/parse/write
```

However, the **one OS thread per client** model does not scale indefinitely. If clients are idle or send very slowly, threads are held for a long time. Use a bounded `ExecutorService`, timeouts/deadlines, quotas, and reject/close policies to avoid unbounded threads/queues. When handlers are dispatched to separate threads, ensure the accepted `SocketChannel` is closed by the proper owner, including when task submission is rejected.

**Write coordination:** a `SocketChannel` supports one concurrent read and one concurrent write according to the API, but multiple writers in the same direction can interleave **logical frames** if they write headers/bodies in multiple steps. Assign a single writer owner, a bounded outbound queue, or a **per-connection** lock covering the entire frame; do not use a single global lock spanning I/O for all clients.

**Shared data synchronization:** maps/sessions/counters used by workers require thread-safe algorithms with proper invariants; `ConcurrentHashMap` does not make a `get→put` sequence an atomic update. Use `compute/merge` or CAS/snapshots/short locks where needed; keep I/O outside locks protecting shared state.

**Send/receive speed:** `ByteBuffer`/direct buffers can help reduce copies in suitable workloads, but buffer pressure, syscall count, connection count, and resource lifecycle matter more than "NIO is always faster than IO." Blocking NIO does not by itself solve slow clients; neither does a selector by itself solve protocol backpressure.

## 16. Common Mistakes When Starting with SocketChannel

1. **"NIO is automatically non-blocking."** False: `SocketChannel` and `ServerSocketChannel` start out blocking. Check `isBlocking()`.
2. **"`open()` means already bound/listening."** False: `ServerSocketChannel.open()` is unbound; you must call `bind(...)` before `accept()`.
3. **"`accept()` always returns immediately."** False in blocking mode: it waits. Only in non-blocking mode does it return `null` when no client is pending.
4. **"The server is non-blocking, so accepted sockets are also non-blocking."** False: an accepted channel **is returned in blocking mode**.
5. **"`read(ByteBuffer)` must fill the buffer."** False: blocking mode only guarantees waiting for at least one byte if space remains, EOF, or an error. To read N bytes, loop until enough bytes arrive according to framing.
6. **"`read` returning `0` means the peer closed."** False: EOF is `-1`; `0` is normal when the buffer has `remaining()==0` or in non-blocking mode when no data is available yet.
7. **"Forgetting `flip()` after receiving bytes."** The parser will see the wrong `position`. After consuming, call `clear` or `compact` as appropriate.
8. **"Calling `flip()` on a buffer returned by `StandardCharsets.UTF_8.encode`."** That buffer is already ready to be read by the channel; flipping it again can discard the region containing valid bytes.
9. **"`clear()` erases bytes in RAM."** False: it only resets the indices; old bytes can still remain in memory.
10. **"One `write` equals one message."** TCP is a byte stream. Define a length-prefix/delimiter and use per-connection parser state.
11. **"Using read-until-EOF for every request."** Easily hangs when both sides keep the socket open; framing defines message boundaries in long-lived connections.
12. **"Switching `configureBlocking(false)` while keeping a blocking `readFully` loop."** `read` can return `0` and the loop will spin. Replace it with readiness + buffer state.
13. **"Calling `Selector.register()` while the channel is still blocking."** Throws `IllegalBlockingModeException`. Switch the channel to non-blocking first.
14. **"`Selector` means each ready event is a complete request."** False: readiness only indicates I/O can make progress; you must still accumulate and parse full frames.
15. **"`socket().setSoTimeout(5000)` is guaranteed to time out `SocketChannel.read`."** Do not rely on that assumption; choose an appropriate timeout/deadline API.
16. **"A channel created from accept can be forgotten without closing."** Leaks connections/file descriptors, increases memory usage, and exhausts resources; manage with try-with-resources/an owner.
17. **"Blocking mode determines server concurrency."** It only defines how **I/O operations wait**; concurrency depends on threads/tasks/event loops and how state is partitioned.
18. **"Writing to a channel means the server has persisted the data."** No; application-level confirmation is required.

## 17. Self-Check Questions

**Question 1.** If you call `ServerSocketChannel.open()` and then `accept()` while forgetting `bind()`, will it automatically listen on port 0? **No.** The channel is unbound; it may throw `NotYetBoundException`.

**Question 2.** You call `server.configureBlocking(false)` and then `accept()` when no client is waiting; what is the result? **`null`**, not EOF or an error.

**Question 3.** A non-blocking listener accepts a connection successfully; what mode will the accepted channel be in? **Blocking**, even though the listener is non-blocking.

**Question 4.** `SocketChannel.read` into a buffer with 1024 bytes remaining returns 3. Were 1021 bytes lost? **No**: `read` is allowed to return fewer bytes than requested; the remaining bytes may arrive in subsequent calls.

**Question 5.** After putting 7 bytes into a `ByteBuffer`, what do you call before passing it to `channel.write(buffer)`? **`flip()`** to set `limit` to 7. If the buffer was returned by `StandardCharsets.UTF_8.encode`, it is already ready to write, so do not perform an extra flip.

**Question 6.** After switching to non-blocking, `read(dst)` returns `0`. Should you call it again in a tight loop? **No.** Retain state and wait for readiness/`OP_READ`.

**Question 7.** Why shouldn't you use a single `read` call to read a 4 + 200 byte length-prefixed frame? **Because TCP does not preserve message boundaries and a single read may return only part of it**; you must read the full header and then the full body.

**Question 8.** To register an accepted channel for `OP_READ` with a selector, what must you do first? **`accepted.configureBlocking(false)`** before registering.

**Question 9.** Does the client's `shutdownOutput()` prevent the client from reading the server's response? **No.** It only half-closes the send direction; the receive direction remains active until close/EOF/error.

**Question 10.** While thread A is blocked in `accept()`, thread B calls `listener.close()`. Is A guaranteed to keep waiting forever? **No**; closing can cause A to receive an exception due to the channel being closed.

## 18. Implementation Checklist and Conclusion

When designing a server with Java NIO, answer in order:

1. **Which channel listens, and which channel carries data?** `ServerSocketChannel` accepts connections; each `SocketChannel` carries a byte stream.
2. **What is the current mode?** Blocking by default; use `isBlocking()` to check, and `configureBlocking(false)` if actually using a selector.
3. **Are bind/connect/accept following the proper lifecycle?** Server binds before accepting; client completes connect before read/write.
4. **Is `ByteBuffer` handled properly with `flip/clear/compact`?** Do not parse bytes outside the valid `position..limit` range.
5. **Are partial reads/writes handled?** Read according to framing, without assuming a single read is enough; when switching to non-blocking, redesign to handle `0`/readiness.
6. **Is there a clear request termination condition?** Length-prefix, delimiter, or EOF defined by the protocol; never guess based on the number of reads.
7. **Is there a policy for timeouts, EOF, interrupts, closes, and malformed frames?** Never block indefinitely in production.
8. **Who owns the channel and buffer?** Bounded workers/queues, one writer per connection when needed, cleanup on all error paths.
9. **If there are many connections, is the chosen architecture appropriate?** Blocking + bounded workers is easy to understand for small/medium scale; non-blocking + selector is useful when managing many sockets/idle connections, though it increases state-machine complexity.
10. **Are you aware of the guarantee level?** TCP preserves byte order but has no message boundaries and does not certify business-level processing after a write.

**Remember:** *NIO is a model of channels + buffers + multiplexing capability; "non-blocking" is a mode that must be enabled explicitly, not the default behavior*. On Java 17, `ServerSocketChannel.accept` and `SocketChannel.read/write` can still operate in standard blocking fashion. Understanding that behavior properly before learning `Selector` will help you avoid both deadlocks and busy-spin loops.

### Official API Documentation

- [Java SE 17 — `ServerSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [Java SE 17 — `SocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Java SE 17 — `SelectableChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html)
- [Java SE 17 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 17 — `Selector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [Java SE 17 — `InterruptibleChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptibleChannel.html).