# Datagrams and Differences from TCP Streams in Java NIO

## 1. The Problem to Understand

When transmitting data over a network, an application may need to send **individual independent messages** or maintain **a continuous byte stream**. Two common models are:

- **Datagram:** each send produces a packet/message with its own boundary. On the Internet, the familiar model is **UDP** (User Datagram Protocol); Java NIO provides `DatagramChannel`.
- **TCP stream:** TCP transmits an **ordered byte stream** between two connected endpoints, without attaching message-boundary semantics to individual write calls. Java NIO typically uses `SocketChannel` and `ServerSocketChannel`.

The key difference is not simply "UDP is fast, TCP is slow". You must understand **message boundaries, connections, reliability, ordering, read/write behavior, data sizes, flow control, security, and application protocol design**.

Lesson goals:

1. Understand what a datagram is and how each datagram carries destination/source addresses.
2. Use `DatagramChannel.send`, `receive`, `bind`, and `connect` in Java NIO.
3. Distinguish datagrams from the byte stream that `SocketChannel` reads/writes.
4. Handle `ByteBuffer`, blocking/non-blocking modes, and `Selector`.
5. Choose UDP/datagrams or TCP appropriately and recognize common design mistakes.

> **Scope:** this is a Java core I/O/NIO lesson focusing on UDP datagram and TCP stream semantics. UDP does not represent every protocol built atop UDP; for example, an upper-layer protocol may add its own authentication, retransmission, or congestion control.

## 2. Two Models Seen from the Application

### UDP datagram: individual standalone messages

An application sends three datagrams:

```text
Sender                         Network                      Receiver

Datagram #1: ["ABC"] ---------\
Datagram #2: ["DEF"] ----------> [may drop / reorder] -----> receive(): one datagram
Datagram #3: ["GHI"] ---------/

Boundaries ["ABC"], ["DEF"], ["GHI"] belong to each packet.
```

One `DatagramChannel.send(buffer, address)` sends the remaining content as **one datagram**. One `receive(buffer)` receives **one datagram** (if available) and returns the sender's address. Two datagrams are never merged into a single `receive` call, nor is one datagram split across subsequent `receive` calls.

However, datagrams can **be lost, arrive late, be duplicated, or arrive out of order**. The sender gets no delivery guarantee merely from `send` returning the byte count sent. A program needing reliability must build its own mechanism or choose an appropriate higher-level protocol.

### TCP: one ordered byte stream

A TCP application performs three write calls:

```text
Sender SocketChannel                      Receiver SocketChannel

write("ABC")
write("DEF")  ----->  TCP byte stream -----> read() may return:
write("GHI")                                "ABCDEF", or
                                            "AB" then "CDEFGHI", or
                                            other chunks
                        Logical content: "ABCDEFGHI"
```

TCP guarantees byte order and retransmission/error-control mechanisms while the connection operates normally, yet **does not preserve boundaries between `write` calls**. A single `read` may return part of a message, multiple messages, or zero bytes in non-blocking mode. The application must define its own framing, such as length prefixes, delimiters, or self-describing formats.

**Core point:** UDP preserves packet boundaries at the API level with no delivery guarantee; TCP provides a reliable ordered byte stream within a connection, without preserving application message boundaries.

## 3. Comparison Table: UDP Datagram vs TCP Stream

| Criterion | UDP / DatagramChannel | TCP / SocketChannel |
|---|---|---|
| Data model | Independent datagrams, each packet has boundaries | Continuous byte stream |
| Connection setup | No handshake required to send UDP | TCP requires connection and handshake before normal exchange |
| NIO send API | `send(ByteBuffer, SocketAddress)`; when connected also `write` | `write(ByteBuffer)` on TCP connection |
| NIO receive API | `receive(ByteBuffer)` returns packet's `SocketAddress` | `read(ByteBuffer)` returns byte count, `-1` on stream EOF |
| Message boundaries | Preserved per datagram; packets larger than receive buffer lose excess | No boundaries per write call; application must frame |
| Delivery guarantee | No guarantee at UDP layer | Retransmission, ordering, and error control while connection is active |
| Ordering/duplication | Packets can reorder, duplicate, or drop | Application sees bytes in order; retransmissions do not surface as duplicates |
| Size | Each datagram has limits; MTU and fragmentation matter | Byte stream has no "MTU-sized message" concept at the API |
| Flow/congestion control | UDP provides no built-in equivalent to TCP | TCP provides flow control and congestion control |
| Detecting unavailable peer | Difficult and inconsistent; successful `send` does not prove receipt | Stateful connection, may observe EOF/error, though failure detection can still lag |
| Broadcast/multicast | UDP suits these mechanisms if OS/network support them | TCP is unicast between two endpoints |
| Selector | `DatagramChannel` supports `OP_READ`, `OP_WRITE` | `SocketChannel` supports `OP_READ`, `OP_WRITE`, `OP_CONNECT` |
| Typical use cases | Telemetry, discovery, game state, real-time with explicit loss policy | Standard HTTP over TCP, streaming RPC, file transfer, ordered reliable data |

This table describes **UDP/TCP at the transport layer**. An application protocol over UDP can add reliability, such as retransmission and congestion control. At that point, the application is **no longer relying on raw UDP** for those properties.

## 4. `DatagramChannel` in Java NIO

`java.nio.channels.DatagramChannel` is a selectable channel for sending/receiving datagrams. Core APIs:

| API | Meaning |
|---|---|
| `DatagramChannel.open()` | Creates a datagram channel with the system-chosen default protocol family |
| `DatagramChannel.open(StandardProtocolFamily.INET)` | Creates an IPv4 channel |
| `bind(SocketAddress local)` | Binds the socket to a local address/port; pass `null` to let the system choose |
| `getLocalAddress()` | Reads the local address/port once bound |
| `send(ByteBuffer src, SocketAddress target)` | Sends one datagram to target |
| `receive(ByteBuffer dst)` | Receives one datagram, returning sender address; may return `null` if non-blocking and none ready |
| `connect(SocketAddress remote)` | Associates a peer address with the UDP channel; not a TCP handshake |
| `read(ByteBuffer dst)` / `write(ByteBuffer src)` | I/O on a **connected** DatagramChannel targeting the configured peer |
| `disconnect()` | Removes the associated peer, with no TCP close handshake |
| `configureBlocking(false)` | Switches to non-blocking mode, registerable with `Selector` |
| `setOption(...)` | Configures supported socket options, such as receive/send buffer sizes |

Typically `Path` goes with `FileChannel`, whereas network addresses go with `SocketAddress` / `InetSocketAddress`. Both are "channels" yet have completely different data APIs.

### Bind and addresses

A UDP server normally binds to a specific port:

```java
try (DatagramChannel channel =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    channel.bind(new InetSocketAddress("127.0.0.1", 9000));
    // Receive datagrams sent to this address/port.
}
```

This is an **illustrative snippet**; port 9000 may already be in use. `127.0.0.1` is IPv4 loopback, suitable only for testing between processes on the same machine. To listen on a real network interface, select an appropriate bind address, firewall rules, and permissions.

Port `0` lets the OS pick an available port, e.g., `new InetSocketAddress(InetAddress.getLoopbackAddress(), 0)`, then retrieving the assigned port via `getLocalAddress()`. This is convenient in automated tests and avoids conflicts on fixed ports.

### Sending datagrams

```java
ByteBuffer outbound = StandardCharsets.UTF_8.encode("PING");
int bytes = channel.send(
        outbound,
        new InetSocketAddress("127.0.0.1", 9000)
);
```

This is an illustrative snippet requiring `ByteBuffer`, `StandardCharsets`, `InetSocketAddress` imports and an open channel. `send` reads bytes from the buffer's `[position, limit)` range and, upon sending, advances the buffer position by the number of bytes sent.

With UDP, the data of one send is treated as **one datagram**, not "an ongoing part of a stream". If the channel is **non-blocking** and cannot send immediately, `send` may return `0`. On network/resource errors or invalid packet size, it may throw `IOException`. Never connect a `send` returning `0` with an assumption that "the first part of the packet was sent"; manage retrying **the same datagram** based on the return value and buffer state.

### Receiving datagrams

```java
ByteBuffer incoming = ByteBuffer.allocate(2048);
SocketAddress source = channel.receive(incoming);

if (source != null) {
    incoming.flip();
    String text = StandardCharsets.UTF_8.decode(incoming).toString();
    System.out.println(text);
}
```

This is also an illustrative snippet. `receive` writes the packet contents into the buffer starting at the current position, updates position, and returns the sender's address. On a non-blocking channel, if no datagram is available, `source == null`; in blocking mode, the call may wait for a packet to arrive.

**Critical boundary:** if a datagram is longer than `incoming.remaining()`, the excess that does not fit is **discarded** per datagram receive semantics; the next `receive` will not fetch "the tail" of that packet. Therefore size the buffer appropriately for the **protocol's maximum message size**, paired with validation/rejection policies for oversized messages. `flip()` switches the buffer to read the newly received bytes, but cannot resurrect truncated bytes.

## 5. Java 17+ Example: Send and Receive over Loopback with DatagramChannel + Selector

A complete example using two `DatagramChannel` instances on the same machine:

1. The receiver binds to an OS-assigned IPv4 loopback port.
2. The receiver switches to non-blocking mode and registers `SelectionKey.OP_READ` with `Selector`.
3. The sender sends one datagram containing the four ASCII bytes `PING`.
4. The selector waits at most 3 seconds to avoid hanging forever if the datagram does not arrive.
5. The receiver receives the datagram and prints its content along with confirmation that a source address was returned.

Create file **`DatagramVsTcpDemo.java`**:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;

public class DatagramVsTcpDemo {
    public static void main(String[] args) throws IOException {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");

        try (DatagramChannel receiver =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             Selector selector = Selector.open()) {

            receiver.bind(new InetSocketAddress(loopback, 0));
            receiver.configureBlocking(false);
            receiver.register(selector, SelectionKey.OP_READ);

            sender.bind(new InetSocketAddress(loopback, 0));

            SocketAddress destination = receiver.getLocalAddress();
            ByteBuffer outbound = StandardCharsets.US_ASCII.encode("PING");

            int sent = sender.send(outbound, destination);
            if (sent != 4 || outbound.hasRemaining()) {
                throw new IOException("Could not send complete PING datagram");
            }

            if (selector.select(3000) == 0) {
                throw new IOException("Timed out waiting for UDP datagram");
            }

            ByteBuffer incoming = ByteBuffer.allocate(128);
            SocketAddress source = receiver.receive(incoming);
            if (source == null) {
                throw new IOException("No datagram available after select");
            }

            incoming.flip();
            String message =
                    StandardCharsets.US_ASCII.decode(incoming).toString();

            System.out.println("Sent bytes: " + sent);
            System.out.println("Received: " + message);
            System.out.println("Sender identified: " + (source != null));
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac DatagramVsTcpDemo.java
java DatagramVsTcpDemo
```

On a machine allowing UDP loopback where the datagram reaches the receiver within the timeout, stdout:

```text
Sent bytes: 4
Received: PING
Sender identified: true
```

Explanation:

- `StandardProtocolFamily.INET` selects IPv4; both channels use `127.0.0.1`.
- Port `0` asks the OS for an available port. `receiver.getLocalAddress()` returns the actual port so the example does not hardcode one.
- `StandardCharsets.US_ASCII.encode("PING")` creates a buffer with four bytes to send. `send` consumes all four bytes, making `outbound.hasRemaining()` `false`.
- The receiver registers `OP_READ`, and `selector.select(3000)` waits up to three seconds. `DatagramChannel` must be in non-blocking mode when registering with a selector.
- `receive(incoming)` returns the sender's `SocketAddress` if a datagram was retrieved; `incoming.flip()` prepares to read the exact bytes received.
- The program does not print the actual address/port because OS-assigned ports vary across runs.
- No separate TCP example is printed/run; differences from TCP are analyzed via diagrams and framing rules below.

**Limitations:** UDP inherently does not guarantee delivery. Even though loopback sends usually succeed, no environment is guaranteed to print this exact stdout; if a firewall, OS, or network resource blocks it, the program throws `IOException`, including on timeout. This intentionally fails loudly rather than hanging forever on a blocking `receive`.

`Selector` reports readiness, without an absolute guarantee in all system states that a packet is definitely waiting when `receive` runs; hence the example still checks `source == null`. In real applications, events and `selectedKeys()` are usually handled in an event loop serving many channels; with a single receiver, the example can check directly after `select` returns a positive count.

## 6. Non-blocking Read/Write and Selector

`DatagramChannel` extends `SelectableChannel`. With `configureBlocking(false)`:

- `receive(dst)` may return `null` when no packet is available.
- `send(src, target)` may return `0` if it cannot send immediately without blocking.
- The channel can be registered with `Selector` using `SelectionKey.OP_READ` and `OP_WRITE`.
- `OP_READ` only reports read readiness at the moment the selector checked; handlers must tolerate no data being present when `receive` actually executes.
- Registering `OP_WRITE` requires careful interest management because sockets are almost always considered writable, causing a CPU spin if enabled continuously without packets queued to send.
- Never use `OP_ACCEPT` on `DatagramChannel` (no TCP accept concept) or `OP_CONNECT` as on `SocketChannel` (UDP `connect` is not a pending TCP handshake).

Typical event-loop structure:

```java
// Illustrative code: channel already configured non-blocking and registered for OP_READ.
while (running) {
    selector.select();

    var iterator = selector.selectedKeys().iterator();
    while (iterator.hasNext()) {
        SelectionKey key = iterator.next();
        iterator.remove();

        if (key.isValid() && key.isReadable()) {
            ByteBuffer packet = ByteBuffer.allocate(2048);
            SocketAddress from = ((DatagramChannel) key.channel())
                    .receive(packet);
            if (from != null) {
                packet.flip();
                // Decode exactly one datagram and process from.
            }
        }
    }
}
```

This **is not a standalone runnable program**; `running`, `selector`, channel setup, buffer management policies, and resource cleanup must be defined externally. The key selection loop merely shows event-loop structure. Real systems must handle exceptions, rate limits, timeouts, malformed packets, and shutdown.

An arriving datagram does not mean the sender performed a handshake. A UDP server needs no `ServerSocketChannel.accept()`; simply binding the channel to the right port suffices to receive messages.

## 7. Connected DatagramChannel Does Not Turn UDP into TCP

`DatagramChannel.connect(remote)` has a name that can mislead. With UDP, `connect` **associates a peer address with the socket**, enables `read(ByteBuffer)` and `write(ByteBuffer)` style I/O, and typically receives datagrams only from that peer per channel semantics. It **performs no TCP handshake**.

Illustrative example:

```java
SocketAddress remote = new InetSocketAddress("127.0.0.1", 9000);

try (DatagramChannel channel =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    channel.connect(remote);

    ByteBuffer request = StandardCharsets.US_ASCII.encode("HELLO");
    channel.write(request);          // Sends a datagram to the connected peer.

    // channel.read(response) reads from this peer; if blocking,
    // it may wait forever since UDP does not guarantee a response.
}
```

This snippet requires the corresponding imports; it will not run standalone as a complete client because there is no server on port 9000.

After `connect`:

- `channel.isConnected()` may return `true`, yet that does not prove the peer is actually alive.
- `read` and `write` use the stored peer address. When unconnected, `read/write` are invalid and throw `NotYetConnectedException`.
- Receiving messages is filtered to the connected peer; do not mistake this for a connection with session state, sequence numbers, and TCP-style retransmission.
- Calling `disconnect()` detaches the peer; the channel remains a datagram channel.
- In some situations, ICMP notifications (such as port unreachable) can trigger `PortUnreachableException`; do not rely on it as a dependable dead-peer detector.

**UDP connect merely simplifies peer addressing**, rather than turning UDP into a reliable stream.

## 8. Datagram Boundaries and Truncation Risk

UDP is message-oriented. Suppose the peer sends a datagram containing `ABCDEFGHIJ` (10 bytes), while the receiver supplies a buffer with only 4 bytes remaining:

```text
Incoming datagram: [A B C D E F G H I J]  (10 bytes)
Receive buffer remaining: 4 bytes

After receive:
  Buffer may contain [A B C D]
  [E F G H I J] of this datagram is discarded.
```

The tail **is not delivered on the next `receive` call** like a byte stream. It is lost at the datagram receive API level. That is why a UDP server must define a maximum message size and choose an adequate receive buffer.

If a protocol needs 1,000-byte payloads, besides allocating a large enough buffer, you can prepend a header with `version`, `messageType`, `messageLength`, and checksum/sequence fields. After receiving, validate total received bytes, header, and `messageLength` before parsing. Avoid trusting client-supplied length values blindly.

### Size limits and MTU

UDP has datagram length limits at the IP/protocol layer; you cannot send an arbitrarily large buffer. IP transmission is also subject to **MTU** (Maximum Transmission Unit):

- Large datagrams may require IP fragmentation (depending on IPv4/IPv6, OS configuration, and path policies).
- Losing a single fragment prevents reassembling the whole datagram, making oversized datagrams more failure-prone in some environments.
- Sending beyond supported sizes can raise errors such as `IOException`/socket failures.
- Practical safe sizes depend on real networks, IPv4/IPv6, and path MTU; do not treat a theoretical constant as a "safe message size on every network".

For real systems, keep messages small enough for the network path, or design application-layer chunking/reassembly with memory limits, timeouts, and validation. Never assume UDP automatically splits a huge application message into small `receive` calls you can concatenate back together.

## 9. Why Does TCP Need Framing?

A TCP stream **does not preserve boundaries between `write` calls**. For example, a server calls:

```java
socketChannel.write(ByteBuffer.wrap(new byte[]{'A', 'B', 'C'}));
socketChannel.write(ByteBuffer.wrap(new byte[]{'D', 'E', 'F'}));
```

This is illustrative only; handle short writes, socket permissions, and channel lifecycles. The client may read `ABCDEF` in one call, or `A` then `BCDE` then `F`, depending on buffer/network states. Never conclude "each `client.read` is one message".

Two fundamental framing approaches:

### Length-prefixed framing

```text
TCP bytes:
[4-byte length N][N-byte payload][4-byte length M][M-byte payload]...

Receiver:
1. Read all 4 length bytes.
2. Decode length using fixed endianness.
3. Verify 0 <= length <= maxMessageSize.
4. Read exact length payload bytes.
5. Repeat for the next message.
```

For example, to use `ByteBuffer.getInt()` for the length, ensure all four bytes have arrived. If only one or two bytes arrived, keep them in the buffer and continue reading; do not treat them as an "incomplete message" and discard them arbitrarily.

### Delimiter framing

```text
HELLO\nWORLD\n
```

The application searches for `\n` to separate messages. When payloads can contain the delimiter, use escaping/encoding; also enforce a line-length limit to stop a client from sending unbounded data with no delimiter.

TCP provides **byte ordering**, not message structure. UDP provides **datagram structure** at the transport layer, yet if an application needs a logical message spanning multiple datagrams, it must define framing/chunking/reassembly at the application layer.

## 10. Reliability, Ordering, and Duplicates over UDP

UDP does not automatically send ACKs, retransmit, or reorder packets for the application. If an application needs these capabilities, an upper-layer protocol can embed metadata inside the payload:

```text
+---------+-------------+-------------+----------------+
| version | sequence No | timestamp   | payload        |
+---------+-------------+-------------+----------------+
```

Example strategies:

1. **Sequence numbers:** distinguish newer/older messages and detect drops or duplicates.
2. **ACK/timeout:** confirm received packets; sender decides when to retransmit after an appropriate timeout.
3. **Idempotency:** when retransmission causes the same action to arrive twice, the receiver does not execute the business operation twice.
4. **Reordering buffer:** hold out-of-order packets when sequential playback/delivery is needed.
5. **Rate/congestion control:** throttle sending rate under network congestion to avoid creating retransmission storms.
6. **Expiration:** for game state/telemetry, stale data should often be dropped rather than retransmitted too late.

However, reimplementing full retransmission, congestion control, ordering, flow control, and security adds considerable complexity. For business data requiring complete ordered bytes, TCP usually saves effort. For real-time traffic, sometimes **dropping old frames to read newer ones** is the actual goal, making UDP/datagrams a better fit.

### TCP also has limitations to keep in mind

- TCP does not guarantee bounded latency or arrival before a deadline.
- TCP retransmissions can spike latency on packet loss, preventing newer data behind a missing byte from being read by the application in stream order (head-of-line blocking).
- A successful `write` return does not guarantee the peer application **processed** the data. TCP acknowledges at the transport layer, not as a business ACK.
- TCP connections can drop, time out, or close halfway; applications still need timeouts, controlled retries, idempotency, and handling for uncommitted work.

## 11. Choosing Java NIO APIs Based on Requirements

| Use case | Approach |
|---|---|
| Local network discovery | `DatagramChannel` + UDP broadcast/multicast if supported, with limits and authentication |
| Periodic telemetry tolerating stale drops | Datagram + sequence/timestamp, rate limiting |
| Continuous game state updates where stale data has little value | Datagram + loss/out-of-order handling |
| Accurate, intact file transfer | TCP stream or another reliable protocol, checksum verification |
| RPC needing complete request/response | Usually TCP or a purpose-built application protocol |
| Many concurrent TCP connections on one thread | `ServerSocketChannel` + `SocketChannel` + `Selector` |
| Many senders sending single packets to one port | `DatagramChannel.bind` + `receive` or `Selector` |
| UDP communicating with one fixed peer | Can use `DatagramChannel.connect(peer)` and `read/write`, though still UDP |
| Needs TLS over a byte stream | TCP + TLS/`SSLEngine` (or suitable network stack); raw UDP has no TLS built in |
| Needs UDP security | DTLS or a vetted protocol; never assume datagrams are authenticated |

Choose protocols at the **application requirements level**: whether loss is acceptable, whether deadlines exist, whether ordering is required, data sensitivity, network environment, and whether NAT/firewalls or multicast must be handled.

## 12. Common Mistakes When Programming DatagramChannel

1. **Assuming `send` succeeding means the receiver got it.** Wrong: UDP has no business ACK, and the network can still drop packets.
2. **Assuming UDP `connect` performs a TCP handshake.** Wrong: it only binds a peer to the datagram socket under UDP semantics.
3. **Using a small receive buffer expecting the next receive to fetch the remainder.** Wrong: bytes exceeding remaining space for that datagram are discarded.
4. **Forgetting `ByteBuffer.flip()` after `receive`.** Buffer position sits after the newly written bytes; decoding before flipping reads the wrong region.
5. **Forgetting message boundaries across multiple datagrams.** Each received packet must be parsed independently or via an explicit reassembly protocol.
6. **Using `read/write` on an unconnected `DatagramChannel`.** Use `send/receive` or connect to a peer first.
7. **Calling `receive` on a blocking channel expecting `null` immediately when empty.** Blocking calls can wait; to poll, use non-blocking mode or a selector/timeout by design.
8. **Not checking `source == null` in non-blocking mode.** When no datagram is available, `receive` can return null.
9. **Forgetting `configureBlocking(false)` before selector registration.** Registering a blocking selectable channel throws `IllegalBlockingModeException`.
10. **Registering `OP_ACCEPT` for DatagramChannel.** UDP has no accept; use `OP_READ`.
11. **Assuming each TCP read returns exactly one message.** TCP is a stream; use framing and byte-accumulation loops.
12. **Sending overly large datagrams.** MTU, fragmentation, and network reliability make large packets unsuitable in many cases.
13. **Not bounding message size/rate.** Packets from untrusted sources can exhaust server CPU or memory.
14. **Using sender address as a security identity.** UDP source addresses can be spoofed or change; use application authentication for sensitive actions.
15. **Assuming UDP is faster than TCP for every problem.** Custom reliability, retries, fragmentation, or packet loss overhead can make it more complex and slower in practice.
16. **Failing to close channels/selectors.** Use try-with-resources, exception handling, and shutdown logic to release sockets and OS resources.

## 13. Thinking Scenarios

### Scenario A: application receiving temperature readings every second

If each new sample supersedes the old value and losing a few samples is acceptable, UDP datagrams are usually reasonable. Attach `timestamp`/`sequence` to discard late or duplicate readings. Never assume datagrams are reliable merely because tests pass cleanly on loopback.

### Scenario B: sending a one-time payment command

Raw UDP is unsuitable if you merely send and assume the transaction succeeded. Payment operations require authentication, idempotency, business confirmation, persisted state, and controlled retries. Use a reliable transport and an application protocol designed to prevent duplicate execution, not the return value of `send`.

### Scenario C: game sending positions 20 times per second

Stale position data becomes irrelevant once newer frames arrive. Datagrams can reduce delays waiting for retransmissions of stale updates, while still requiring sequence numbers, loss handling, sensible send rates, and a more reliable channel for critical state synchronization.

### Scenario D: sending two messages over TCP

The sender executes `write("HELLO")` and `write("WORLD")`. The receiver reads `"HELLOWORLD"` in one call. That is completely normal TCP behavior. If two messages are needed, use framing such as `[length=5][HELLO][length=5][WORLD]`.

### Scenario E: receiving a 1,500-byte packet into a 512-byte buffer

The receiver cannot fetch the remaining 988 bytes in the next `receive` call. It must size receive buffers and protocol limits properly up front, or reject oversized packets. Truncated bytes cannot be recovered by `flip` or reading again.

### Scenario F: UDP client wanting to avoid processing packets from other peers

`DatagramChannel.connect(remote)` can filter by peer address and offer a simpler `read/write` API. It still does not cryptographically authenticate the sender, does not guarantee the remote peer will reply, and does not replace encryption/anti-spoofing.

## 14. Self-Check Questions

**1.** Send two UDP datagrams: `"AB"` and `"CD"`. Can the receiver assume a single `receive` will return `"ABCD"`?  
**No.** Each receive handles one datagram; packets can drop or reorder, but UDP never merges two datagrams into one message.

**2.** Write `"AB"` then `"CD"` over TCP. Can the receiver get `"ABCD"` in a single `read`?  
**Yes.** TCP is a byte stream and does not preserve boundaries between two writes.

**3.** Why does `channel.receive(buffer)` return `SocketAddress` instead of just a byte count?  
**Because** an unconnected DatagramChannel receiving a packet must provide the source address to the application. Byte count can be computed from the increase in `ByteBuffer.position()` (recorded before receive).

**4.** If the channel is non-blocking and no datagram is ready, what does `receive` return?  
**It can return `null`.** Do not dereference the source address without checking the result.

**5.** After `DatagramChannel.connect(peer)`, does the sender automatically get packet-loss retransmission?  
**No.** It is still UDP.

**6.** If a datagram has 1,000 bytes while `dst.remaining() == 100`, will ten receive calls read all 1,000 bytes?  
**No.** Excess bytes that do not fit in the buffer are discarded during that datagram receive.

**7.** Which tool can wait for packets on a non-blocking receiver?  
**`Selector`** registered with `OP_READ`; or polling with an appropriate strategy. Never use `OP_ACCEPT`.

**8.** Does TCP prevent an application from sending a duplicate command when the client retries?  
**Not automatically at the business layer.** TCP protects the stream within one connection, yet application retries across requests or new connections can still submit an operation twice. Use idempotency when it matters.

## 15. Key Takeaways

- **UDP datagram = packet-level message boundaries, no delivery/ordering guarantees.**
- **TCP = ordered byte stream with reliable delivery mechanics, no message boundaries in the API.**
- **`DatagramChannel.send`/`receive` operates one datagram at a time**, `receive` returns the sender's address; an undersized buffer drops the excess of the packet.
- **`DatagramChannel.connect` is not a TCP handshake**; UDP does not magically become a reliable stream.
- **`SocketChannel.read/write` needs framing and partial I/O handling** when the application works with discrete messages.
- **`Selector` works well with non-blocking DatagramChannel**, especially for multi-socket event loops.
- When choosing UDP vs TCP, prioritize requirements for latency, loss tolerance, ordering, message size, security, and protocol complexity.

### API Documentation

- [DatagramChannel — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [SocketChannel — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [ServerSocketChannel — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [Selector — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [ByteBuffer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
