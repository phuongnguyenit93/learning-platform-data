# SocketChannel, ServerSocketChannel, and DatagramChannel in Java NIO

## 1. Three Network Channels Solving Three Different Needs

Java NIO (`java.nio.channels`) provides channels for network communication via `ByteBuffer`. The three key types are:

- **`SocketChannel`:** endpoint of a byte-stream connection, typically **TCP**. It can act as a client or as a connection channel accepted by a server.
- **`ServerSocketChannel`:** connection-listening endpoint, typically a **TCP server**; calling `accept()` obtains a new `SocketChannel` for a specific client.
- **`DatagramChannel`:** sends/receives packets with message boundaries (datagrams), typically **UDP**; no TCP connection is required.

All use `ByteBuffer`, are `SelectableChannel` instances, and can operate in **blocking** or **non-blocking** mode, fitting both simple code and a `Selector` event loop. However, their data semantics and lifecycles differ: **TCP is an ordered stream, while UDP is a datagram protocol with packet boundaries**.

Orientation table:

| Criterion | `SocketChannel` | `ServerSocketChannel` | `DatagramChannel` |
|---|---|---|---|
| Role | Read/write over a connection | Listen and accept connections | Send/receive datagrams |
| Typical protocol | TCP | TCP | UDP |
| Application data | Byte stream, no message boundaries | Does not directly carry payload | Each datagram preserves packet boundaries |
| Typical API | `connect`, `finishConnect`, `read`, `write` | `bind`, `accept` | `bind`, `send`, `receive`, `connect`, `read`, `write` |
| Non-blocking | `connect` may be pending; `read/write` may return 0 | `accept` may return `null` | `receive` may return `null`; `send` may return 0 |
| When server accepts a TCP client | Is the channel just returned by `accept()` | Continues listening for other clients | No concept of TCP `accept()` |

In Java 17, the `SocketChannel` and `ServerSocketChannel` APIs also support **Unix-domain sockets** when using the appropriate protocol family/address and a supported platform. This article focuses on Internet **TCP/UDP** sockets on loopback to avoid assuming every implementation supports only a single protocol family.

## 2. The TCP Model: One Listener, Many Connection Channels

A TCP server can be visualized as follows:

~~~text
Client A: SocketChannel --TCP--> SocketChannel A
                                      ^
                                      |
Client B: SocketChannel --TCP--> SocketChannel B
                                      ^
                                      |
                            ServerSocketChannel
                          (listen on IP + port)
                          accept() returns new channel
~~~

`ServerSocketChannel` **is only a listener**. Each time `accept()` succeeds, the server receives a **dedicated `SocketChannel`** for that connection. To read/write client A's data, the server calls `read/write` on channel A, not on `ServerSocketChannel`.

### 2.1. Server-side steps

1. Open `ServerSocketChannel.open()`.
2. Call `bind(localAddress)` to listen on an address and port.
3. Call `accept()` to accept a connection.
4. For the accepted `SocketChannel`, use `read`/`write` with a `ByteBuffer`.
5. Close the client channel when done, and close the listener when stopping the server.

Illustrative snippet (inside a method handling `IOException`):

~~~java
try (ServerSocketChannel server = ServerSocketChannel.open()) {
    server.bind(new InetSocketAddress("127.0.0.1", 8080));
    try (SocketChannel peer = server.accept()) {
        // peer is the dedicated connection for the newly accepted client.
        ByteBuffer received = ByteBuffer.allocate(1024);
        int count = peer.read(received);
        // Must check count and handle data framing.
    }
}
~~~

The code above can **block indefinitely** at `accept()` or `read()` if there is no client or matching data. This is a usage illustration, not the standalone demo in section 6.

### 2.2. Client-side steps

~~~java
try (SocketChannel client = SocketChannel.open()) {
    client.connect(new InetSocketAddress("127.0.0.1", 8080));
    ByteBuffer bytes = StandardCharsets.UTF_8.encode("hello");
    while (bytes.hasRemaining()) {
        client.write(bytes);
    }
}
~~~

This is an illustrative snippet; it requires a matching TCP listener, imports, and exception handling. By default, a channel is **blocking**, so `connect` waits until the connection is established or fails. Only call `read/write` after connecting; if not yet connected, a `NotYetConnectedException` may be thrown.

## 3. TCP Is a Byte Stream, Not Java Message Packets

One of the most common mistakes is assuming that one `write` corresponds to an exact single `read` on the other side. TCP only guarantees an ordered byte stream while the connection is operating normally; it **does not preserve application write boundaries**.

For example, the client calls:

~~~text
write("HELLO")
write("WORLD")
~~~

The server might read the data in chunks such as:

~~~text
read -> "HEL"
read -> "LOWOR"
read -> "LD"
~~~

Or many other splits, as long as the byte order is preserved. Even a single `read(ByteBuffer)` call in blocking mode does not guarantee filling the entire buffer.

### 3.1. Reading with ByteBuffer

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);
int n = channel.read(buffer);

if (n == -1) {
    // EOF: the peer has ended its sending side/the stream is exhausted.
} else if (n > 0) {
    buffer.flip(); // prepare to read exactly the newly received bytes
    // Parse data in [position, limit).
    buffer.clear(); // prepare the buffer for the next receive round
}
~~~

Illustrative snippet with a connected `SocketChannel channel`. `read` returns:

- **`n > 0`:** n bytes were read and the buffer's `position` advances by n.
- **`n == 0`:** can occur, especially in non-blocking mode when no bytes are ready to receive; must not be treated as EOF.
- **`n == -1`:** the incoming side of the stream has reached end-of-stream (e.g., the peer closed/`shutdownOutput`).

In real parsing code, **do not call `clear()` and discard incomplete message bytes**. If a new frame contains partial data, use `compact()` to retain the leftover bytes and continue reading. `clear()` only resets buffer state and does not physically erase content.

### 3.2. Writing must check remaining

~~~java
ByteBuffer data = StandardCharsets.UTF_8.encode("hello");
while (data.hasRemaining()) {
    channel.write(data);
}
~~~

`write` returns the number of bytes actually consumed from the buffer; this may be fewer than the initial `remaining`. In particular, a non-blocking `write` may return **0** if the socket output buffer is not yet ready. Do not busy-spin when non-blocking returns 0: wait for `OP_WRITE` via `Selector` or structure a controlled retry mechanism.

In blocking mode, the loop above expresses the intent to "send all data in the buffer", but **does not guarantee the peer has read/processed the data**, nor does it add message boundaries on its own.

### 3.3. Protocol framing

Because TCP has no message boundaries, the application must choose **protocol framing**, for example:

- Each message terminated by a newline (must specify the charset and handle newlines inside payloads).
- A 4-byte length prefix followed by that exact number of body bytes, with specified endianness and size limits.
- Fixed-length messages (only suitable when the schema defines a fixed length).
- Protocols with built-in framing such as HTTP/2 or WebSocket (handled according to their specifications).

For example, a parser for a 4-byte length prefix cannot assume a single `read` will obtain all 4 bytes. It must retain state across reads, cap the length to avoid excessive allocations, and distinguish EOF mid-frame.

## 4. ServerSocketChannel: bind, accept, and Multiple Clients

`ServerSocketChannel.open()` creates an unbound listener. Calling `bind`:

~~~java
ServerSocketChannel server = ServerSocketChannel.open();
server.bind(new InetSocketAddress("127.0.0.1", 0));
InetSocketAddress address =
        (InetSocketAddress) server.getLocalAddress();
~~~

This is an illustrative snippet that does not yet close `server`; production code must own and close resources. Port **0** asks the OS to allocate an available ephemeral port, helping tests avoid hardcoding ports 8080/9000. The address `127.0.0.1` only accepts connections on the same machine; a wildcard address may accept connections across multiple interfaces and requires network security consideration.

`accept()` has two behaviors:

- **Blocking mode (default):** typically waits until a client arrives and returns a new `SocketChannel`, unless an error/close/interrupt occurs.
- **Non-blocking mode:** if no connection is pending acceptance, returns `null`; when a connection is available, returns the channel.

`ServerSocketChannel` itself does not perform TCP payload `read`/`write`. Accepted sockets exist independently. Closing the listener does not mean a program has closed every accepted channel; the server must manage the lifecycle of each connection.

### Non-blocking connection of SocketChannel

A `SocketChannel` can be opened in non-blocking mode:

~~~java
SocketChannel client = SocketChannel.open();
client.configureBlocking(false);
boolean connected = client.connect(remote);

if (!connected) {
    // Connection is pending; wait for OP_CONNECT using Selector.
    // When ready, call client.finishConnect().
}
~~~

This is an illustrative snippet: `remote` must be an appropriate `SocketAddress`, and the channel must be closed when finished. `connect()` may immediately return **`true`** if the connection completes at once; if it returns **`false`**, you must not read/write as a connected channel. When the connectable signal arrives (or at an appropriate time), `finishConnect()` completes the connection; in non-blocking mode it may also return `false` while still pending. A failed connection throws an appropriate `IOException`.

`SocketChannel.isConnectionPending()` and `isConnected()` help observe the current state, but do not replace `finishConnect()` when a connection is still in progress.

## 5. DatagramChannel: UDP Send/Receive and Packet Boundaries

Unlike TCP, UDP has **datagram boundaries**. One send is one datagram and one receive returns **one datagram**. There is no reliability guarantee: packets can be lost, duplicated, arrive out of order, or arrive too late. The application must handle these itself if it requires acknowledgement, retries, sequencing, or deduplication.

### 5.1. UDP server and client without accept

~~~text
DatagramChannel sender                       DatagramChannel receiver
    send(buffer, remote) --- UDP datagram ---> receive(buffer)
                                                |
                                                +-- returns source SocketAddress
~~~

`DatagramChannel` can use `send(ByteBuffer, SocketAddress)` and `receive(ByteBuffer)` when **not connected**. Typically, the receiver calls `bind(localAddress)` to listen on a stable port; the sender can be automatically bound by the OS on first send.

~~~java
try (DatagramChannel udp = DatagramChannel.open()) {
    udp.bind(new InetSocketAddress("127.0.0.1", 9999));
    ByteBuffer packet = ByteBuffer.allocate(2048);
    SocketAddress from = udp.receive(packet);
    packet.flip();
    // Process exactly one datagram and the sender's address 'from'.
}
~~~

This is an **illustrative snippet**: UDP data must be sent to port 9999 for `receive()` to return in blocking mode. Do not assume packets have a maximum length of 2048; if an incoming datagram is **larger than the ByteBuffer's `remaining()`**, the excess is **silently discarded** per the Javadoc. Therefore, choose a receive buffer size suitable for the protocol and MTU/payload limits.

### 5.2. Return values to distinguish

- `receive(dst)` returns the source **`SocketAddress`** when a datagram arrives; in non-blocking mode it returns **`null`** when no packet is available.
- `send(src, target)` returns the **number of bytes** sent. In non-blocking mode, it may return **0** when the output buffer has no room for the datagram.
- A successful `send` does not mean the peer received, processed, or ACKed it.
- Call `dst.flip()` after receive before decoding; `receive` advances `position` by the number of bytes copied.

**Do not mechanically adapt TCP stream-reading loops that concatenate bytes into a frame and apply them to UDP:** UDP already has datagram boundaries; an oversized packet truncated in the receive buffer loses that packet's data rather than leaving "the rest to arrive in the next `receive()`".

### 5.3. DatagramChannel "Connect" differs from TCP

`DatagramChannel.connect(peerAddress)` **does not establish a TCP session and performs no reliable handshake**. It associates the UDP channel with a default peer: receiving datagrams only from that peer, sending to that peer, and allowing `read`/`write` (which take no address parameter). An unconnected UDP channel still uses `send/receive`.

After `disconnect()`, the channel can send/receive to and from appropriate addresses via `send/receive`. With UDP, one `write` corresponds to one datagram per the channel's semantics, not a byte stream merged with multiple other `write` calls.

## 6. Complete Java 17+ Example: Mini TCP Echo + UDP Loopback

The demo runs in **one process** using OS-assigned ports so no separate server startup is needed. The TCP flow creates a listener, connects a client, calls `accept` on the server, and exchanges `ping/pong` (each message is exactly four bytes in the example). The UDP flow sends one `hi` datagram from sender to receiver over loopback.

**File name: `NetworkChannelsDemo.java`**

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;

public class NetworkChannelsDemo {
    private static void sendAll(SocketChannel channel, String value)
            throws IOException {
        ByteBuffer data = StandardCharsets.UTF_8.encode(value);
        while (data.hasRemaining()) {
            channel.write(data);
        }
    }

    private static String readExactly(SocketChannel channel, int size)
            throws IOException {
        ByteBuffer data = ByteBuffer.allocate(size);
        while (data.hasRemaining()) {
            if (channel.read(data) == -1) {
                throw new EOFException("Truncated TCP message");
            }
        }
        data.flip();
        return StandardCharsets.UTF_8.decode(data).toString();
    }

    public static void main(String[] args) throws IOException {
        // 1. TCP: listener + client + accepted SocketChannel.
        try (ServerSocketChannel listener = ServerSocketChannel.open();
             SocketChannel client = SocketChannel.open()) {
            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            client.connect(listener.getLocalAddress());

            try (SocketChannel accepted = listener.accept()) {
                sendAll(client, "ping");
                System.out.println(
                        "tcp server: " + readExactly(accepted, 4));

                sendAll(accepted, "pong");
                System.out.println(
                        "tcp client: " + readExactly(client, 4));
            }
        }

        // 2. UDP: each send corresponds to one datagram.
        try (DatagramChannel receiver =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            receiver.bind(new InetSocketAddress("127.0.0.1", 0));
            sender.send(
                    StandardCharsets.UTF_8.encode("hi"),
                    receiver.getLocalAddress());

            ByteBuffer packet = ByteBuffer.allocate(16);
            SocketAddress source = receiver.receive(packet);
            packet.flip();

            System.out.println("udp source? " + (source != null));
            System.out.println(
                    "udp message: " + StandardCharsets.UTF_8.decode(packet));
        }
    }
}
~~~

Compile and run in the directory containing the source file:

~~~bash
javac NetworkChannelsDemo.java
java NetworkChannelsDemo
~~~

**Stdout when TCP/UDP loopback works normally on the machine:**

~~~text
tcp server: ping
tcp client: pong
udp source? true
udp message: hi
~~~

Explanation:

1. `listener.bind(..., 0)` opens an OS-chosen TCP port, while `client.connect(listener.getLocalAddress())` connects to the listener on the same machine.
2. `accept()` returns a `SocketChannel` representing the server-side connection; `client` and `accepted` are the two endpoints of one TCP connection.
3. `sendAll` loops until the `ByteBuffer` is completely sent. `readExactly` also loops until **exactly four bytes** are read; this avoids assuming a single `read` always gets the whole message. This is only a fixed-length protocol for illustration, not a variable-length message parser.
4. The `DatagramChannel` sender sends one `hi` datagram. The receiver receives it, prints whether a source address exists, and decodes the two bytes.
5. `try-with-resources` closes all channels, even if an exception occurs.

**Demo limitations:** uses TCP/UDP in the same process over loopback, avoiding external network issues. In environments that completely block socket permissions, TCP/UDP bind/connect may fail. The program has no timeouts because the goal is a short example that works reliably when loopback is active; production code needs timeouts, cancellation, and network error handling. The four-byte fixed-length TCP format is agreed upon in advance by both sides and is not general framing for arbitrary payloads.

## 7. Blocking, Non-blocking, and Selector

The channels above are `SelectableChannel` instances. By default they are in **blocking mode**. Calling `configureBlocking(false)` switches to non-blocking mode (when not constrained by an incompatible `Selector` registration).

| Operation | Blocking | Non-blocking |
|---|---|---|
| `ServerSocketChannel.accept()` | Waits for a connection, then returns `SocketChannel` | No connection yet ⇒ returns `null` |
| `SocketChannel.connect(remote)` | Waits for connection success or failure | May return `false`; requires `finishConnect()` |
| `SocketChannel.read(dst)` | Typically waits for at least one byte or EOF when buffer has space | No data yet ⇒ may return 0 |
| `SocketChannel.write(src)` | May wait on output buffer; still should check remaining | May write partially or return 0 |
| `DatagramChannel.receive(dst)` | Waits for a matching datagram | No datagram yet ⇒ returns `null` |
| `DatagramChannel.send(src, remote)` | Sends datagram or reports error | May return 0 if packet cannot be sent yet |

With many connections, one thread can manage an event loop using `Selector`:

~~~text
Selector.select() -> selectedKeys
   OP_ACCEPT  -> listener.accept()
   OP_CONNECT -> client.finishConnect()
   OP_READ    -> socket.read(...) or datagram.receive(...)
   OP_WRITE   -> socket.write(...) remaining bytes in the queue
~~~

This is a conceptual diagram. Each `SelectionKey` is bound to a registered channel; real code must check key validity, handle exceptions, byte framing, backpressure, and close the channel/selector. On a non-blocking channel:

- When `accept() == null` or `receive() == null`, do not treat it as an error or EOF.
- When `SocketChannel.read() == 0`, keep the partial reading state and wait for more data.
- When `SocketChannel.write() == 0`, keep the `ByteBuffer` with remaining data to continue writing on an appropriate event.
- If `OP_WRITE` remains registered continuously even when no bytes are waiting to be written, the selector can repeatedly report writable and cause a CPU busy loop.

Note that **non-blocking I/O does not automatically turn TCP into UDP**, does not add message boundaries, and does not guarantee network operations complete immediately.

## 8. Closing Connections, EOF, Timeouts, and Network Errors

### 8.1. Channel lifecycle

These channels implement `AutoCloseable`, so use `try-with-resources`. For TCP:

- `SocketChannel.close()` closes the entire connection on the channel side.
- `SocketChannel.shutdownOutput()` ends the writing side while allowing continued reading. The peer typically sees EOF after preceding bytes have been processed by TCP.
- `SocketChannel.shutdownInput()` ends the reading side; subsequent reads return `-1` by contract.
- `SocketChannel.read(...) == -1` indicates **EOF of the TCP stream**, not an empty message.
- The listener and accepted sockets have separate lifecycles: closing the listener **does not replace** closing the managed client channels.

`DatagramChannel` has no "EOF due to peer close" like a TCP byte stream. Going a long time without receiving UDP **does not prove** the peer closed; datagrams can be lost, blocked, or simply not sent yet.

### 8.2. InterruptibleChannel

`SocketChannel`, `ServerSocketChannel`, and `DatagramChannel` all implement `InterruptibleChannel`. For a thread blocked in I/O:

- Another thread calling `channel.close()` can cause the blocked operation to throw `AsynchronousCloseException`.
- Another thread calling `thread.interrupt()` closes the channel and causes the blocked operation to throw `ClosedByInterruptException`, with the thread's interrupt flag set.

If the channel was already closed before the I/O operation started, `ClosedChannelException` may be thrown. Exceptions such as `NotYetConnectedException`, `AlreadyConnectedException`, `ConnectionPendingException`, `BindException`, `ConnectException`, and other `IOException` types convey different state or connection failures and must be handled per situation. Never catch an interrupt exception and try to reuse a channel that has already been closed.

### 8.3. Timeouts and backpressure

Production code must have policies for:

- Appropriate connection/read wait limits, e.g., non-blocking combined with `Selector.select(timeout)`, scheduling deadlines, or corresponding timeout APIs; do not assume `configureBlocking(false)` automatically provides timeouts.
- For TCP, if a producer sends faster than a consumer reads, maintain a queue of remaining `ByteBuffer` instances with memory limits/backpressure.
- For UDP, set reasonable datagram sizes and handle loss/reordering/duplicates at the protocol layer if needed; sending many bytes does not mean they automatically split into safe datagrams matching your message schema.
- Avoid having multiple threads mutate the same `ByteBuffer` without synchronization. SocketChannel allows one concurrent read and one concurrent write, but shared application buffer state must still be protected by the application.
- Control connection counts, file descriptors/socket handles, and close all accepted channels on shutdown.

## 9. Choosing TCP or UDP Based on Data Requirements

**Choose TCP/SocketChannel + ServerSocketChannel** when the application needs to transmit an **ordered byte stream with transport-layer reliability**: streaming request/response, file transfers, session-based protocols. However, you must design framing, timeouts, concurrency/dispatching, and protection against slow peers yourself.

**Choose UDP/DatagramChannel** when the application wants to operate on **individual datagrams**, accepts possible loss/duplication/reordering, or implements its own recovery: telemetry, service discovery, real-time data depending on the protocol. Consider MTU, payload limits, source spoofing prevention, and network risks.

Some modern protocols build reliability on top of UDP using custom logic; thus using UDP does not mean every application built on it must accept data loss. The core difference is **which guarantees are provided out of the box by the transport layer** versus what must be handled in the application protocol layer.

## 10. Common Mistakes

1. **Calling `read/write` on `ServerSocketChannel` as if it were a TCP connection.** The listener only calls `accept`; read/write happens on the accepted `SocketChannel`.
2. **Thinking every TCP `write` corresponds to one `read`.** TCP is a stream; you need framing and buffer loops.
3. **Treating `SocketChannel.read()==0` as EOF.** EOF is `-1`; `0` means no bytes were read.
4. **Failing to check `hasRemaining()` after `write`.** Data may still remain in the buffer, especially in non-blocking mode.
5. **Using a busy-spin loop when non-blocking `write()==0`.** You need readiness management and backpressure.
6. **Not calling `finishConnect()` after non-blocking `connect()==false`.** The connection is still pending; do not read/write as if connected.
7. **Calling `accept()` in non-blocking mode and assuming it cannot be `null`.** When no client is waiting, `null` is normal.
8. **Confusing UDP `connect` with a TCP handshake.** UDP connect sets a default peer/source filter; it provides no stream or delivery guarantee.
9. **Using a UDP buffer that is too small and expecting the remainder on the next receive.** Excess bytes of that datagram are truncated **and discarded**.
10. **Assuming a successful UDP `send` means the peer received it.** It does not confirm delivery or processing.
11. **Forgetting `flip` or `compact` when reading ByteBuffer.** The parser may read 0 bytes, read stale bytes, or lose an incomplete frame.
12. **Closing only ServerSocketChannel and forgetting accepted sockets.** The listener channel and client channels have separate lifecycles.
13. **Assuming every environment allows binding a fixed port.** Ports may be busy or blocked by policy; loopback tests should use port 0.
14. **Assuming non-blocking solves all timeouts and error handling.** Applications still need deadlines, queues, EOF/error handling, and shutdown logic.

## 11. Self-Check Questions

**Question 1.** Why can a TCP client call `write("A")` and `write("B")` twice while the server receives `"AB"` in a single `read()`?

**Answer:** TCP provides an ordered byte stream and does not preserve boundaries of individual application `write` calls. Framing is required to separate messages.

**Question 2.** With `ServerSocketChannel` in non-blocking mode, what does `accept()` return when no client is waiting?

**Answer:** `null`. This is not a connection error; the application continues the event loop waiting for `OP_ACCEPT`.

**Question 3.** `SocketChannel.connect(remote)` returns `false` in non-blocking mode. What is the next step?

**Answer:** The connection is still pending; wait for connectable readiness and call `finishConnect()` until the connection completes or throws an error. Do not read/write while not yet connected.

**Question 4.** A 120-byte datagram arrives at `DatagramChannel.receive(dst)` when `dst.remaining()==32`. Can the remaining 88 bytes be retrieved in the next `receive`?

**Answer:** No. Data exceeding the receive buffer's remaining space for that datagram is discarded by contract; the next `receive` will read a different datagram.

**Question 5.** Why is the result of `udp.send` insufficient to confirm the server received the data successfully?

**Answer:** UDP has no transport-layer ACK/delivery guarantee; `send` only indicates the local send action. If confirmation is needed, the application protocol must add it.

### Official Java 17 Documentation

- [SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [DatagramChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [SelectableChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html)
- [Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
