# DatagramChannel: sending/receiving, UDP connection, and interacting with ByteBuffer in Java

`java.nio.channels.DatagramChannel` is an NIO channel for exchanging **UDP datagrams** using `ByteBuffer`. Unlike `SocketChannel` which uses TCP, `DatagramChannel` can send/receive **without connecting beforehand**; when calling `connect(remote)`, the channel binds to a specific UDP peer to use `read()/write()` conveniently, but **does not create a TCP handshake and does not prove that the remote machine exists or has a listening application**.

Three important knowledge groups to master at the same time:

1. **Datagram:** each send call creates a UDP message with its own boundary, not a continuous byte stream like TCP.
2. **Channel:** a channel can be unconnected (using `send/receive`), or logically connected to a peer (additionally having `read/write`); supports blocking/non-blocking and `Selector`.
3. **ByteBuffer:** `position`, `limit`, `capacity`, and the steps `put → flip → send`, `receive → flip → get → clear` determine which bytes are transmitted and read.

The lesson includes a complete Java 17+ program that sends/receives both styles over IPv4 loopback without depending on the Internet, and then explains truncation, non-blocking, UDP connection, error management, and production design.

## 1. UDP datagrams and the meaning of DatagramChannel

TCP provides an ordered byte stream. UDP provides **distinct datagrams**: each packet has a source address, source port, destination address, destination port, and payload. If a sender sends two datagrams `A` and `B`, the receiver must not treat them as a continuous stream and does not automatically merge them into a single message. UDP does not guarantee delivery, ordering, non-duplication, or application-layer ACKs.

`DatagramChannel` is an abstract class in `java.nio.channels`; create a channel using a factory method:

~~~java
// Java 17+ fragment inside a method handling IOException.
try (DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    // INET = IPv4 protocol family.
}
~~~

With `StandardProtocolFamily.INET`, the program requests an IPv4 socket. `StandardProtocolFamily.INET6` is for the IPv6 family on supported systems. `DatagramChannel.open()` lets the provider choose the default protocol family and address support appropriate for the runtime; you should not assume every environment chooses the same protocol.

A newly created `DatagramChannel` is by default **open, unconnected**, and in **blocking mode** unless changed with `configureBlocking(false)`. The channel may need to bind to a local port before receiving; `send()`/`receive()`/`connect()` on an unbound channel may cause the OS to automatically bind an available address/port, per the API. For a server that wants to receive on a specific port, call `bind()` explicitly.

Main APIs:

| Function | Method | When to use |
| --- | --- | --- |
| Create UDP channel | `DatagramChannel.open(...)` | Choose protocol family / open channel |
| Bind local IP/port | `bind(SocketAddress)` | Receiver on a fixed port, or sender wanting a stable source IP/port |
| Unconnected send | `send(ByteBuffer src, SocketAddress target)` | Each datagram can specify its destination |
| Unconnected receive | `receive(ByteBuffer dst)` | Returns the **source address** of the datagram |
| Attach UDP peer | `connect(SocketAddress remote)` | Communicate only with the specified peer; use `read/write` |
| Connected write | `write(ByteBuffer src)` | Send a datagram to the connected peer |
| Connected read | `read(ByteBuffer dst)` | Read a datagram from the connected peer |
| Detach peer | `disconnect()` | Return to unconnected mode |
| Change I/O mode | `configureBlocking(false)` | Non-blocking + `Selector` |
| Close resource | `close()` | Release socket/channel |

**The word "connect" in UDP has a different meaning than in TCP.** A UDP channel can set a remote peer for the socket on the local machine without negotiating a connection over the network. `isConnected()==true` only states that the channel is open and has been attached to a peer per the API, not an indicator that the peer is online.

## 2. Unconnected mode: `send()` and `receive()`

A UDP server receiving datagrams typically binds to a port and calls `receive`:

~~~java
// Java 17+ fragment; requires imports for java.net, java.nio, java.nio.channels.
try (DatagramChannel receiver =
        DatagramChannel.open(StandardProtocolFamily.INET)) {

    receiver.bind(new InetSocketAddress(50000));

    ByteBuffer input = ByteBuffer.allocate(2048);
    SocketAddress peer = receiver.receive(input); // Blocking by default.
    input.flip();

    byte[] bytes = new byte[input.remaining()];
    input.get(bytes);
    String message = new String(bytes, StandardCharsets.UTF_8);

    System.out.println("From " + peer + ": " + message);
}
~~~

This snippet is **not a standalone program** and will **block** if no datagram has arrived yet. `receiver.receive(input)` copies the datagram into the buffer starting at `input.position()`, advances position by the number of bytes received, and returns the packet's source address. If the buffer does not have enough space, the remainder is **discarded** (see section 6).

The sender does not need to connect beforehand:

~~~java
// Java 17+ fragment; target is a verified InetSocketAddress.
ByteBuffer output = StandardCharsets.UTF_8.encode("HELLO");
int sent = sender.send(output, target);
~~~

`StandardCharsets.UTF_8.encode(...)` returns a `ByteBuffer` already ready to **read** (position/limit frame the exact encoded bytes), so pass it directly to `send` without calling `flip()` again. The `send` method uses **all remaining bytes** as **one UDP datagram**. If sending succeeds, the source buffer's position advances to limit.

In blocking mode, `send` waits for local buffer conditions if needed; in non-blocking mode, if there is not enough space to send, it can return `0`. The Java 17 Javadoc specifies that the returned byte count is **all of the initially remaining bytes**, or `0` in non-blocking mode when it cannot send immediately; it must not be designed like TCP by sending the remaining part of the datagram as a subsequent packet. If the payload is sent, it is **one** datagram at the time of the call. A successful `send` is not an ACK from the receiver.

### Source address of a datagram

`receive(dst)` returns the `SocketAddress` from the packet; for regular IP, you can cast to `InetSocketAddress` after checking the type and then read `getAddress()/getPort()`. In an unconnected request-response protocol, you typically reply by calling `send(reply, source)` to return to the sender's IP and UDP port.

Validate the payload size and packet contents before using the source address for any privileged action. A UDP source address does not prove application identity. On some networks, the UDP source IP can be spoofed; sending large unbounded replies easily causes traffic amplification.

## 3. Connected UDP: `connect()`, `read()`, and `write()`

When communicating with only **one peer**, you can call:

~~~java
// Java 17+ fragment inside a method that throws IOException.
channel.connect(peer);
System.out.println(channel.isConnected()); // true if channel is still open and connected.

ByteBuffer request = StandardCharsets.UTF_8.encode("PING");
int sent = channel.write(request);

ByteBuffer response = ByteBuffer.allocate(1024);
int received = channel.read(response);
response.flip();

channel.disconnect();
~~~

**What `connect(peer)` does:**

- Configures the remote IP and port for the socket. Datagrams received from **other addresses/ports** are not delivered to the connected channel.
- Enables `read(ByteBuffer)` and `write(ByteBuffer)` because there is no need to pass source/destination addresses on every call.
- `getRemoteAddress()` reflects the currently configured peer; `isConnected()` indicates the **logical connection state at the local socket**.
- May **discard datagrams already in the receive buffer** prior to `connect()`. You should not rely on pending received data being preserved across the mode switch.
- If the socket is not yet bound, `connect` automatically binds a system-assigned local address/port.

**What `connect(peer)` does not do:**

- Does not perform a SYN/SYN-ACK/ACK handshake like TCP, and does not wait to confirm a remote UDP service exists.
- Does not turn UDP into a mechanism guaranteeing delivery, ordering, retransmission, or a byte stream.
- Does not verify that the remote server is ready or that an application session has been authenticated.

Once connected, `write` sends **one datagram** to the attached peer; `read` receives a datagram from that peer. Calling `read()/write()` when the channel is **not connected** throws `NotYetConnectedException`. `receive/send` remain callable APIs on a connected channel, but the send destination must match the peer; calling `send(src, otherTarget)` throws `AlreadyConnectedException` if the destination differs from the peer. Do not try to call `connect()` again while already connected; to switch peers, call `disconnect()` first, then `connect(newPeer)`.

With connected UDP, the operating system may report `PortUnreachableException` when it receives an ICMP message indicating the remote port is unreachable; the API **does not guarantee** that every non-listening peer will produce this exception. Therefore, do not use a successful `write` or `isConnected` returning true as a liveness check for the peer.

## 4. ByteBuffer: `capacity`, `position`, `limit`, and `remaining`

`DatagramChannel` methods transfer data from/to `ByteBuffer`; misunderstanding buffer state can cause you to send **0 bytes**, send stale data, or print bytes that do not belong to the datagram just received.

| Property | Meaning | Example with a new `ByteBuffer.allocate(16)` |
| --- | --- | --- |
| `capacity()` | Fixed capacity of the buffer | `16` |
| `position()` | Next relative read/write position | `0` |
| `limit()` | Current upper bound for reading/writing | `16` |
| `remaining()` | `limit - position` | `16` |
| `flip()` | Switch from **written/fill** mode to **read/drain** mode: `limit=position` then `position=0` | After `put(4 bytes)`: `limit=4, position=0` |
| `clear()` | Prepare for new write/fill: `position=0, limit=capacity` | `position=0, limit=16` |
| `rewind()` | Re-read data within the current limit: `position=0` | Used to re-read without clearing the limit state |
| `compact()` | Move **unread** bytes to the beginning of the buffer and prepare for further writing | Useful for stream/partial processing; should not be used to merge different datagrams |

Main invariant: `0 ≤ position ≤ limit ≤ capacity`. A buffer can be allocated on the heap with `allocate()` or in direct memory with `allocateDirect()`. Not every buffer has `array()`; for example, direct buffers typically do not have an accessible Java array. When decoding, use `get(byte[])` or a decoder that supports `ByteBuffer`.

### Sending from a manually filled buffer

~~~java
// Fragment: fill manually, then switch to read mode.
ByteBuffer out = ByteBuffer.allocate(32);
out.put("OK".getBytes(StandardCharsets.UTF_8));
out.flip();  // position=0, limit=2
int n = channel.send(out, destination);
~~~

If you forget `flip()` after `put`, position is at the end of the data just written, while limit may equal capacity. `send` will take the **remaining** portion from the current position to limit, potentially sending unprepared bytes. For `ByteBuffer.wrap(byte[])` or `StandardCharsets.UTF_8.encode("OK")`, the buffer already has the right position/limit for reading, so **do not flip it again**: flipping again at position 0 sets limit to 0 and makes the message empty.

### Receiving into a buffer and decoding

~~~java
// Fragment: dst is a cleared or newly allocated buffer.
ByteBuffer dst = ByteBuffer.allocateDirect(2048);
SocketAddress source = channel.receive(dst);
if (source != null) {
    dst.flip(); // Only the newly received bytes lie from 0 to limit.
    byte[] bytes = new byte[dst.remaining()];
    dst.get(bytes);
    String text = new String(bytes, StandardCharsets.UTF_8);
    dst.clear(); // Prepare for the next datagram; does NOT erase physical bytes.
}
~~~

A fresh buffer has `position=0, limit=capacity` and receiving data advances position. `flip()` after receive sets limit to the exact byte count, so `get` retrieves only the datagram's content. `clear()` allows overwriting on the next call **rather than wiping sensitive contents**; do not use `clear()` as a sanitization method. Old data remains in the backing memory until overwritten or handled by another mechanism.

## 5. Standalone Java 17+ program over UDP loopback

This example creates two IPv4 `DatagramChannel`s and binds them to loopback `127.0.0.1` on ephemeral ports. First the unconnected sender sends `PING` with `send()` and the receiver receives it with `receive()`; then **both channels connect to each other's address** and use `write()/read()` to transmit `OK`. All I/O operations run on the same thread to reduce timing factors: the program sends first and then reads each packet.

**Save as `DatagramChannelDemo.java`:**

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.charset.StandardCharsets;

public class DatagramChannelDemo {
    private static String takeUtf8(ByteBuffer input) {
        byte[] bytes = new byte[input.remaining()];
        input.get(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});

        try (DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel receiver =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {

            sender.bind(new InetSocketAddress(loopback, 0));
            receiver.bind(new InetSocketAddress(loopback, 0));

            // 1) Unconnected: send(buffer, target).
            ByteBuffer out = StandardCharsets.UTF_8.encode("PING");
            int sent = sender.send(out, receiver.getLocalAddress());
            System.out.println("sendBytes=" + sent);
            System.out.println(
                    "sourceRemaining=" + out.remaining());

            // Use direct buffer: do not rely on dst.array().
            ByteBuffer in = ByteBuffer.allocateDirect(64);
            SocketAddress from = receiver.receive(in);
            System.out.println(
                    "expectedSource="
                            + from.equals(sender.getLocalAddress()));
            System.out.println(
                    "receivePosition=" + in.position());

            in.flip();
            System.out.println("unconnectedText=" + takeUtf8(in));

            in.clear(); // position=0, limit=capacity=64
            System.out.println(
                    "afterClear=position:" + in.position()
                            + ",limit:" + in.limit());

            // 2) UDP connect: pin peer, still no TCP handshake.
            sender.connect(receiver.getLocalAddress());
            receiver.connect(sender.getLocalAddress());
            System.out.println(
                    "connected=" + (sender.isConnected()
                            && receiver.isConnected()));

            ByteBuffer next = StandardCharsets.UTF_8.encode("OK");
            int written = sender.write(next);
            int n = receiver.read(in);
            in.flip();

            System.out.println("writeBytes=" + written);
            System.out.println("readBytes=" + n);
            System.out.println("connectedText=" + takeUtf8(in));

            sender.disconnect();
            receiver.disconnect();
            System.out.println(
                    "disconnected=" + (!sender.isConnected()
                            && !receiver.isConnected()));
        }
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac DatagramChannelDemo.java
java DatagramChannelDemo
~~~

**Expected output in an environment allowing UDP loopback** (verified with JDK):

~~~text
sendBytes=4
sourceRemaining=0
expectedSource=true
receivePosition=4
unconnectedText=PING
afterClear=position:0,limit:64
connected=true
writeBytes=2
readBytes=2
connectedText=OK
disconnected=true
~~~

Explanation in order:

1. Sender sends UTF-8 `PING`, 4 bytes long. `send` transfers all 4 bytes of `out`, leaving `remaining()==0`.
2. Receiver receives a packet from the sender's exact local socket: `receive` returns the source address, and the direct buffer has `position==4`. Comparing source with the sender's address returns `true` because both bound directly to `127.0.0.1` with OS-chosen ports.
3. `flip()` restricts the readable region to 4 bytes, decoded as `PING`.
4. `clear()` resets the 64-byte buffer to a ready-to-receive state; no need to allocate a new buffer.
5. Both sockets are attached to a UDP peer and `isConnected()==true`. Sender `write`s 2 bytes `OK`; receiver `read` returns 2, then `flip`s and decodes accordingly.
6. `disconnect()` clears the peer configuration on both channels; `isConnected()==false`. The `try-with-resources` block calls `close()` on both channels.

**Do not misinterpret the result:** the example runs on the **same machine** with tiny packets and no external network firewall; it tests the NIO API, buffers, and UDP loopback, and **does not prove UDP always reaches its destination over the Internet**. If a sandbox environment blocks loopback sockets, the program may throw `IOException` or hang; that is an environment limitation, not a change in method semantics.

## 6. UDP datagram boundaries and truncation risk with a small ByteBuffer

With TCP, a `read` call does not correspond to one message; applications usually need to assemble bytes into frames. With UDP, one successful `send` is **one datagram**; one successful `receive` receives data from **one datagram** and returns the source.

However, when a datagram contains 2,000 bytes while the buffer only has 512 bytes `remaining()`:

~~~text
Sender: [------------------ 2000 bytes ------------------]
                            UDP datagram
Receiver: ByteBuffer.remaining() = 512

receive(dst)
  -> copies at most 512 bytes into dst
  -> the remainder of the same datagram is discarded
  -> cannot call receive() a second time to get that "remainder"
~~~

According to the `DatagramChannel.receive` and `read` Javadoc, if the remaining bytes in the buffer are insufficient, **the excess of the datagram is silently discarded**. Therefore:

- Check `buffer.remaining()` **before** `receive`; if position has not been reset, the actual remaining capacity is reduced.
- Set appropriate protocol size limits; for example, a discovery message of at most 1,024 bytes, allocate at least that boundary, and validate all length fields.
- After `receive`, if `position == capacity`, it **may** be full or truncated; you cannot rely on this alone to prove the datagram was definitely truncated (a datagram matching capacity exactly also ends at the final position).
- If payloads exceeding safe network limits are needed, design application-layer fragmentation/reassembly or choose an appropriate protocol. Avoid relying on IP fragmentation because losing one fragment affects the entire UDP datagram.

**ByteBuffer does not merge UDP boundaries for you.** `compact()` is useful for keeping unread bytes of a stream, but should not be used by default to concatenate different datagrams into one message without an explicit protocol layer. If each datagram is an independent message, finish processing it, `clear()`, and receive the next packet.

### UTF-8 data and byte counts

A Vietnamese character can take multiple UTF-8 bytes. `ByteBuffer.remaining()` is a **byte count**, not a Java character count. If a packet is truncated in the middle of a UTF-8 sequence, decoding may replace malformed bytes with a replacement character or report an error depending on the decoder policy. For strict protocols, verify packet length, encoding, and decoder error policy before using the content.

For binary bodies, use `ByteBuffer.putInt/getInt`, `putLong/getLong`, and `order(ByteOrder.BIG_ENDIAN/LITTLE_ENDIAN)` according to the specified format. ByteBuffer defaults to big-endian; decoding is only accurate when both sender and receiver follow the conventions for byte order, data types, and datagram boundaries. Do not arbitrarily convert binary data via `new String(..., UTF_8)`.

## 7. Blocking and non-blocking: key differences to remember

By default, a channel is opened in **blocking mode**:

- `receive(dst)` may **block** until a valid datagram arrives (or an error/channel close occurs).
- `read(dst)` when the channel is **connected** may block waiting for a datagram from the peer.
- `send(src,target)`/`write(src)` may block until the local output buffer allows sending the packet.

After `channel.configureBlocking(false)`:

- `receive(dst)` returns `null` when no datagram is available at the time of the call. Having no packet **is different from** an empty datagram: receiving a 0-byte datagram can return a source and leave position unchanged.
- `read(dst)` on a connected channel can return `0` when no data is immediately available; do not treat `0` as TCP EOF or an error.
- `send(src,target)`/`write(src)` can return `0` when there is no space to send immediately. Do not busy-spin or split an unsent packet into smaller packets by slicing the buffer.
- If the channel uses a `Selector`, the event loop can wait for `OP_READ`/`OP_WRITE` instead of dedicating a blocking thread per socket.

A non-blocking **fragment** example, not standalone:

~~~java
// channel is already opened, bound, and configureBlocking(false).
ByteBuffer dst = ByteBuffer.allocate(2048);
SocketAddress source = channel.receive(dst);

if (source == null) {
    // No datagram available right now.
    // Wait for OP_READ via Selector or an appropriate scheduling mechanism.
} else {
    dst.flip();
    // Process only bytes from position to limit.
}
~~~

Do not abuse `while (channel.receive(dst) == null) { }`: it creates a busy-spin, burns CPU, and provides no real deadline or backpressure.

### Selector, registration, and timeout

A channel must be in non-blocking mode to register with a `Selector`:

~~~java
// Java 17+ fragment; channel is bound, selector is open.
// imports: java.nio.channels.*, java.nio.ByteBuffer.
channel.configureBlocking(false);
channel.register(selector, SelectionKey.OP_READ);

int readyKeys = selector.select(2_000); // Wait up to ~2 seconds.
if (readyKeys == 0) {
    // No channels ready in this polling cycle.
} else {
    for (SelectionKey key : selector.selectedKeys()) {
        if (key.isValid() && key.isReadable()) {
            DatagramChannel readable = (DatagramChannel) key.channel();
            ByteBuffer buffer = ByteBuffer.allocate(2048);
            SocketAddress source = readable.receive(buffer);
            if (source != null) {
                buffer.flip();
                // Process one received datagram; guard workload.
            }
        }
    }
    selector.selectedKeys().clear();
}
~~~

This is a **conceptual pattern for one event loop cycle**, not a production server: you must organize selector/channel lifecycle, processing backlog limits, subsequent receives, I/O errors, close conditions, and resources. `select(timeout)` does not set a "UDP connection timeout"; it only limits how long the event loop waits for readiness events. Read readiness does not necessarily guarantee a subsequent call will read a packet, due to races or state changes; non-blocking code must still handle `null`.

**Note:** do not use `DatagramChannel.socket().setSoTimeout(...)` as if it were the standard way to control `DatagramChannel.receive()`. For NIO I/O, use non-blocking + selector/deadline or proper channel cancellation/closing design; when using regular `DatagramSocket.receive()`, `setSoTimeout` is a different API with the socket adaptor's own semantics.

## 8. Connected UDP does not guarantee liveness, delivery, or response

An application sometimes makes a flawed inference:

~~~java
// Anti-pattern: cannot confirm the peer is alive using this flag.
channel.connect(remote);
if (channel.isConnected()) {
    // Wrong to conclude "the remote server is definitely receiving packets".
}
~~~

UDP connect only configures the peer and handles address filtering at the local/OS level. A server does not need to call `accept()` for UDP. A typical UDP server calls `bind(localPort)` and then `receive()`; there is no listen backlog or TCP handshake. Even if `write()` returns the number of bytes sent and `isConnected()==true`, the datagram can still be lost, dropped by a firewall, routed to an unintended interface, or reach an app that does not process it.

To verify **that the peer/app has replied**, you must have a request-response protocol with message IDs, deadlines, verification that the response matches the request, controlled retries, and duplicate protection. For example:

~~~text
UDP CLIENT                                    UDP SERVER
send datagram: requestId=42  --------------> receive requestId=42
                                              validate & process
receive datagram: requestId=42 <------------ send responseId=42
       |
       +-- matching id, valid data, expected source?
       +-- no response before deadline -> business timeout
       +-- timeout does not prove the previous request was not processed
~~~

**The application protocol determines reliability**, not the word "connected" in a method name. If the application uses UDP for operations with side effects (payments, DB writes, etc.), retries need an idempotency key or deduplication by request ID; otherwise, a request may be processed multiple times.

### Peer address, NAT, and security

`connect()` restricts the peer by the IP/port pair observed at the socket. NAT can change external ports; a peer can restart on a new port, and packets from other pairs are filtered out. Filtering by IP/port **is not cryptographic authentication** and is not enough to trust that the sender is authorized. For sensitive data, you need authentication, integrity, and encryption at the appropriate layer, or a designed protocol such as DTLS/QUIC when it fits the problem.

## 9. Comparing DatagramChannel and DatagramSocket

| Criterion | `DatagramChannel` | `DatagramSocket` |
| --- | --- | --- |
| Sent/received data | `ByteBuffer` | `DatagramPacket` combined with `byte[]` |
| Unconnected | `send(src,target)` / `receive(dst)` | `send(packet)` / `receive(packet)` |
| Connected peer | `connect(remote)`; uses `read/write` | `connect(remote)`; still uses `send/receive` on packets |
| Non-blocking + Selector | Yes, with `configureBlocking(false)` | Traditional `DatagramSocket` API has no corresponding `Selector` registration |
| Packet scope | Each `send/receive` handles one datagram | Each `send/receive` handles one datagram |
| Buffer | Direct/heap `ByteBuffer`, position/limit | Array/payload inside `DatagramPacket` |
| When to use | NIO applications, event loop integration, managing many sockets | Simple examples, small blocking UDP applications |

**Do not assume DatagramChannel is always faster than DatagramSocket.** Speed depends on packet volume, JVM/OS, buffers, allocation strategy, processing workload, batching, network, and architecture. You can use `channel.socket()` to obtain a `DatagramSocket` adapter, but do not form the false expectation that all blocking mode/timeout configurations will behave identically to a standalone socket.

## 10. Real-world errors and how to handle them

### 10.1. `NotYetConnectedException`

Calling `channel.read(dst)` or `write(src)` without calling `connect(remote)` first. Fix: use `receive(dst)` and `send(src,target)` when unconnected; or `connect(remote)` first if the protocol has only one peer.

### 10.2. Sending empty packets or garbage bytes due to forgetting `flip()`

After `buffer.put(bytes)`, `position` has advanced past the data; you must call `flip()` before `send/write`. Conversely, `StandardCharsets.UTF_8.encode(...)` already returns a buffer in read mode: if you flip it again immediately, limit can become 0 and send an empty payload. Check `position/limit/remaining` right before each send.

### 10.3. Printing garbage or `\\u0000` characters after receiving

This can happen from decoding the entire buffer capacity (e.g., `new String(buffer.array())`) instead of **the exact number of datagram bytes**. After receiving, call `flip()` and read `remaining()`. With a direct ByteBuffer, `array()` can also throw `UnsupportedOperationException`. Using `get(byte[])` as in the example works for both heap and direct buffers.

### 10.4. Losing the tail of a datagram

Receiving with a buffer whose `remaining` is smaller than the payload causes the excess to be discarded, and it cannot be read by another `receive()` call. Increase the size appropriately, and check the format and payload length. Do not confuse this behavior with a TCP stream that requires multiple reads.

### 10.5. `receive()` blocks forever

The channel is blocking and no valid datagram arrives. Check that the server `bind()`s to the right local port, the sender targets the right destination, firewall/routing, whether a `connect`ed socket only accepts one peer, and selector state. For deadlines, use non-blocking + selector or proper cancellation/closing, not busy polling.

### 10.6. `isConnected()==true` but no response

Connected UDP does not check the peer and does not retry. Verify the IP/port is correct, the server is bound to that port, firewall/NAT, message schema, and application-layer timeout. Do not treat `PortUnreachableException` as a mandatory signal in every missing-server scenario.

### 10.7. Two different peers cannot communicate through a connected channel

A channel that called `connect(peerA)` only receives/sends with A's address/port. When you need to talk to B, use an unconnected channel with `send/receive` or `disconnect()` and then reconfigure another peer. Note that datagrams buffered before connect may be dropped.

### 10.8. Selector always reports ready but CPU is high

Check whether `OP_WRITE` is kept enabled continuously when there is no data left to send, whether `selectedKeys().clear()/remove` is called properly, whether a readable channel has not been drained, or whether blocking work is running inside the event loop. Prioritize events and backpressure; do not use the event loop to run long DB/CPU tasks.

## 11. Designing a safe datagram service

When moving toward a real service, apply these principles:

1. **Specify sizes:** clear max payload, version, message type, length, and encoding. Never receive an unvalidated payload and allocate memory based on an arbitrary length field. The theoretical maximum UDP size depends on IPv4/IPv6/IP headers; to reduce fragmentation, most protocols should choose small datagrams suited to path MTU rather than trying to send near 65 KB.
2. **Preserve packet boundaries:** process each datagram independently, validate before parsing. Do not assume ordering or that every send guarantees a receive.
3. **Apply deadlines:** if sending requests, set a response wait limit and a retry/backoff policy. A timeout does not prove the peer did not process the request.
4. **Prevent replays and duplicates:** include request IDs, idempotency for interactions with side effects, and message authentication when needed.
5. **Optimize allocations:** you can reuse `ByteBuffer` across the processing lifecycle, but avoid passing the same buffer to multiple workers for concurrent reads/writes without synchronization; direct buffers do not help if allocated continuously.
6. **Control source/destination:** hosts and ports must be verified, considering IPv4/IPv6, NAT, routing, firewalls, and policies. A UDP source address does not self-authenticate identity.
7. **Protect the event loop:** avoid unintended blocking; cap work per cycle, per-client quotas, max packets/bytes, and overload mechanisms.
8. **Close resources properly:** use `try-with-resources`, handle `IOException`/closed channel, and do not use buffers/frames after the message lifecycle has ended.
9. **Observability:** record received/sent/failed datagram counts, byte sizes, source/target, timeouts, queue lengths, dropped/oversize packets, processing time, and parse errors; do not log sensitive payloads by default.
10. **Verify in real environments:** a loopback demo does not represent NAT, Wi-Fi, packet loss, reordering, MTU, containers, or firewalls. Test with simulated packet loss/latency in a controlled test environment.

Especially with `ByteBuffer`, most bugs arise from **forgetting read/write direction and the remaining region**. Name variables clearly such as `outboundReadyToRead`, `inboundToFill`, or use encode/decode methods to control state instead of passing an anonymous buffer across multiple layers that all mutate position.

## 12. Extended exercises and self-check

**Exercise A — Reading buffer state:** A `ByteBuffer.allocate(8)` has four bytes `put` into it, then `flip()`. What are `position/limit/remaining`?  
**Answer:** `0/4/4`. After `send` succeeds for 4 bytes, `position=4` and `remaining=0`. `clear()` resets to `0/8/8` without erasing data in backing memory.

**Exercise B — Distinguishing modes:** An unconnected channel needs to send `HELLO` to port 9000 on an IP; which method should be called?  
**Answer:** `send(ByteBuffer, SocketAddress)`. `write(ByteBuffer)` requires `connect(remote)` first.

**Exercise C — UDP connection:** `channel.connect(remote)` returns normally and `channel.isConnected()==true`. Does this guarantee the remote host is listening on that UDP port?  
**Answer:** No. This is a local peer configuration with no TCP handshake; only receiving a valid protocol response helps evaluate the peer/app at test time.

**Exercise D — Truncation:** A datagram is 1,400 bytes long; the receiver has 1,000 bytes free. Will calling `receive(dst)` twice retrieve all 1,400 bytes?  
**Answer:** No. The first receive copies at most 1,000 bytes; the remainder of the first datagram is discarded, and the next call reads a different datagram if one exists.

**Exercise E — Non-blocking:** Does `receive(dst)` returning `null` prove the sender did not send a packet?  
**Answer:** No. It only indicates that at the time of the call, no datagram was immediately available on the non-blocking channel. The packet may arrive later or be blocked/lost on the network.

**Exercise F — Zero-length datagram:** `receive(dst)` returns a source, but `position` does not increase. Can such a datagram exist?  
**Answer:** Yes. A UDP datagram can have a 0-byte payload; do not use `position==0` as a substitute for `source==null` to check whether a packet was received.

**Exercise G — Reusing a buffer:** After receiving a 6-byte packet into a buffer of capacity 32, what must be done to receive the next independent datagram?  
**Answer:** `flip()` to read the exact 6 bytes, process or copy the data you need to keep, then `clear()` to prepare to fill a new packet. Do not `compact()` to merge two independent UDP packets.

**Exercise H — Switching peers:** A channel is connected to A and needs to send to a different B. Can you call `send(src,B)` directly?  
**Answer:** No; per the connected channel API, a destination different from the peer leads to `AlreadyConnectedException`. Use an unconnected channel, or `disconnect()` then `connect(B)` when the design requires it.

**Exercise I — Why use a direct buffer in the demo?**  
**Answer:** To show how to retrieve data properly via `position/limit/get` without relying on `array()`. Not because a direct buffer is guaranteed to be faster in every case.

**Exercise J — What needs to be added to turn the demo into a real-world UDP request-response?**  
**Answer:** Frame/version format, input validation, request IDs, receive deadlines, retry/backoff, duplicate handling, max payload, steps to validate the response source, and real-network testing.

## Official documentation

- Java SE 17 — `DatagramChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html
- Java SE 17 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 — `Buffer` (position, limit, flip, clear, rewind): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html
- Java SE 17 — `Selector`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html
- Java SE 17 — `SelectionKey`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html
- Java SE 17 — `StandardProtocolFamily`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardProtocolFamily.html
- Java SE 17 — `PortUnreachableException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/PortUnreachableException.html
