# Sending UDP with a Small Buffer: Observing Data Truncation and Datagram Boundaries in Java 17

## 1. Experimental Problem: Sending 12 Bytes, Why Are Only 5 Bytes Received?

Suppose a program sends a UDP datagram with ASCII content:

```text
ABCDEFGHIJKL
```

The receiver uses a **5-byte** `byte[]`. The typical output when running on loopback is:

```text
Send:       ABCDEFGHIJKL  (12 bytes in one UDP datagram)
Receive #1: ABCDE         (5 bytes copied into the buffer)
Remainder:       FGHIJKL   (7 bytes discarded, NOT queued for the next receive)

Send next:  xyz           (another UDP datagram)
Receive #2: xyz           (3 bytes of the second datagram)
```

**UDP preserves message/datagram boundaries**: each successful receive via `DatagramSocket.receive(DatagramPacket)` or `DatagramChannel.receive(ByteBuffer)` retrieves **one datagram**, not an arbitrary number of bytes from a continuous stream. If the destination buffer cannot hold the entire datagram, the excess bytes that cannot be copied **are discarded**, not carried over to the next `receive` call.

This contrasts with how TCP `InputStream.read()` works: TCP provides a **byte stream**, where a single `read` can read part of an application message and subsequent reads retrieve the rest from the same stream; UDP provides **discrete datagrams**, where each datagram carries a payload with its own boundary.

**Short conclusion:** Sending a UDP datagram larger than the receive buffer → results in **a truncated datagram**, not a datagram automatically split across multiple `receive` calls. Calling `receive` again will not recover the lost portion. To receive the full data, design appropriate datagram/buffer sizes or an application-level protocol.

In this lab, we intentionally send short payloads over `127.0.0.1`, inspect the actual bytes, test both `DatagramSocket` and `DatagramChannel`, and distinguish three commonly confused concepts: **sent datagram length**, **receive buffer capacity**, and **OS socket buffer size**.

## 2. What Is UDP and Why Do Datagram Boundaries Matter?

A UDP datagram can be visualized as:

```text
┌───────────────────────────────────────────┐
│ UDP header (8 bytes)                      │
├───────────────────────────────────────────┤
│ Application payload: A B C D E F ... L    │
└───────────────────────────────────────────┘
             1 datagram
```

UDP identifies peers by source/destination IP and port, transporting independent datagrams. One send via `DatagramSocket.send(packet)` typically corresponds to **one UDP datagram** containing the data described by `DatagramPacket`. In NIO, `DatagramChannel.send(buffer, target)` sends the remaining data in the source buffer as **one datagram** when the send operation succeeds.

Key characteristics to keep in mind:

- **Boundary-preserving:** Datagram 1 and datagram 2 are not merged into a single "byte stream" at the UDP receive API.
- **No delivery guarantee:** Datagrams can be lost due to network issues, full queues, routing errors, filters, or other causes.
- **No ordering guarantee:** If A is sent before B, there is no general guarantee that B will not arrive before A.
- **No deduplication guarantee:** Across different protocol layers and implementations, the application must handle duplicates, retries, and idempotency itself.
- **No TCP-style reliability/retransmission:** If a datagram is lost or truncated at the application buffer, a subsequent `receive` call does not retrieve the missing bytes.
- **Practical payload limits:** IP/UDP headers, MTU, fragmentation, and platform limits affect the recommended send size.
- **Receive-buffer truncation is a receiver-side issue:** Even when the network delivers the full datagram to the host, an application with too small a buffer will only observe the leading portion.

This example does **not** test reliability over the Internet. Loopback reduces network variables so API behavior is easy to observe, but a passing loopback test does not turn UDP into a guaranteed-delivery protocol.

### Receive Flow Diagram

```text
Application sender
    send("ABCDEFGHIJKL")  ──────▶  UDP datagram #1, length = 12
                                      │
                                      v
                                 Kernel UDP receive
                                      │
                                      v
                             application receive cap=5
                                      │
                                      ├── copied bytes = "ABCDE"
                                      └── excess bytes = "FGHIJKL" DISCARDED

    send("xyz")           ──────▶  UDP datagram #2, length = 3
                                      │
                                      v
                             next application receive
                                      └── copied bytes = "xyz"
```

**There is no "remaining half-datagram" left in the UDP receive queue** after the first receive. This differs from TCP's partial read mechanism.

## 3. Distinguishing Four Sizes and Three Types of Buffers

| Name | Where It Lives | Practical Meaning |
|---|---|---|
| **UDP payload length** | The datagram created by the sender | Number of application bytes sent in a single datagram |
| **`DatagramPacket` receive length** | Receiver-side Java object | Maximum bytes ready to be received into the packet; after `receive`, `getLength()` returns the number of bytes received |
| **`byte[]` backing storage** | Application heap memory | Array capacity; the usable region also depends on the offset and packet receive length |
| **`ByteBuffer.remaining()`** | NIO buffer when calling `DatagramChannel.receive` | Number of available bytes from `position` to `limit` for the current datagram |
| **`SO_RCVBUF` / receive buffer size** | OS socket-level receive queue/buffer | Capacity to buffer datagrams before the application reads them; not the Java receive array size |
| **`SO_SNDBUF` / send buffer size** | Socket/OS | Capacity to buffer outbound data; does not dictate how large the receiver's `byte[]` will be |
| **Path MTU** | Network path/IP | IP packet size that can traverse the path without fragmentation |

The "small buffer" experiment here mainly refers to the **application receive buffer**: `new byte[5]` or `ByteBuffer.allocate(4)`. Do not increase `setReceiveBufferSize(1_000_000)` and assume a 5-byte `DatagramPacket` will magically hold 12 bytes. The two buffer types serve different roles.

### Java Receives Payloads as a Unit

With `DatagramSocket`:

```java
byte[] bytes = new byte[5];
DatagramPacket received = new DatagramPacket(bytes, bytes.length);
socket.receive(received);
int copied = received.getLength(); // number of bytes copied into the packet
```

With `DatagramChannel`:

```java
ByteBuffer bytes = ByteBuffer.allocate(4);
SocketAddress remote = channel.receive(bytes);
int copied = bytes.position(); // assumes initial position = 0
bytes.flip();                  // prepare to read the newly received bytes
```

These two snippets are **API illustrations**, not standalone programs (the `socket`, `channel` variables and imports must be provided). The complete runnable program is in Section 6.

## 4. `DatagramPacket`: Buffer, Offset, Length, and Safe Reuse

Key APIs in `java.net.DatagramPacket`:

| Method | Meaning |
|---|---|
| `getData()` | Returns the **backing array**; not a copy trimmed to the exact received byte count |
| `getOffset()` | Starting index of valid data in the backing array |
| `getLength()` | Length of data to send, or number of bytes received after `receive` |
| `setLength(int)` | Sets the packet's byte limit for the corresponding send/receive, not exceeding the backing capacity |
| `setData(byte[], offset, length)` | Replaces the array/offset/length as intended |
| `getAddress()`, `getPort()` | Source IP address and port of the newly received datagram (when receiving) |

### Read Only the Valid Data Region

**Wrong:**

```java
// Intentionally incorrect code when using a newly received packet:
String value = new String(packet.getData(), StandardCharsets.UTF_8);
```

The array may contain stale/garbage bytes outside the newly received range, or the packet may use `offset > 0`. For known UTF-8 text where all bytes have been received, bound the exact range:

```java
String value = new String(
        packet.getData(),
        packet.getOffset(),
        packet.getLength(),
        StandardCharsets.UTF_8);
```

Even this statement **does not prove the data is complete**: if the UDP datagram is larger than the receive region, the text may be truncated, possibly even mid-UTF-8 code point. The protocol layer must validate length/format before trusting the data.

### Should You Call `setLength` Again When Reusing?

When reusing a receive `DatagramPacket`, set the **desired receive limit** before each `receive`:

```java
packet.setLength(packet.getData().length - packet.getOffset());
socket.receive(packet);
```

This explicitly expresses "next time, allow receiving up to the remaining capacity of the array," avoiding accidentally keeping a smaller cap set by your own code earlier. When `getOffset()` is used, do not call `setLength(array.length)` if the offset is positive because `offset + length` would exceed the array bounds.

**Important detail:** do not mechanically conclude that "receiving a 3-byte datagram causes all subsequent receives to automatically be capped at 3 bytes just because `getLength()==3`." How an implementation tracks internal capacity may differ from what you infer from the received length property. In the actual lab run, **we explicitly call `setLength(3)`** to narrow the limit in turns #3 and #5; therefore, truncation in those turns is intentional and verifiable, not reliant on an assumption about reuse.

If you want absolute simplicity, you can allocate a **new packet for each receive**, accepting the allocation cost; for high-throughput datagram streams, reusing buffers/packets reduces allocations but requires proper handling of ownership, concurrency, and metadata.

### Do Not Split One DatagramPacket Across Two Receive Calls

After `receive`, `getLength()` only reports the **number of bytes copied into the packet**. When it equals capacity, it **does not confirm completeness**. Nor does this high-level API provide an OS-specific **"truncated" flag like `MSG_TRUNC`**. The next receive retrieves a new datagram if one is available, not the remainder of the previous datagram.

## 5. Designing an Internet-Independent Experiment

We use:

- **IPv4 loopback `127.0.0.1`**, requiring no DNS or external host.
- Receiver `DatagramSocket` bound to port **0** so the OS assigns an available ephemeral UDP port; the sender uses `receiver.getLocalPort()` as its destination.
- Sender and receiver created upfront, each time **sending exactly one datagram then receiving it**. This keeps datagram observation deterministic in program order without relying on bursting multiple datagrams simultaneously.
- `receiver.setSoTimeout(2000)` prevents `receive` from blocking forever if a packet is lost or the OS blocks UDP; the test fails clearly instead of hanging.
- A single 5-byte backing array with one `DatagramPacket` to test various receive capacities.
- Then a separate `DatagramChannel` pair with `ByteBuffer.allocate(4)`.
- For ASCII data, character count equals byte count so results are easy to read; for Unicode, print **hex bytes** so UTF-8 truncation errors are not masked by replacement characters from a decoder.
- Each result is verified with `AssertionError` if it differs from expectations; no "false PASS" just because the code printed a string.

The turns:

| Turn | Sent Datagram | Sent Length | Receive Cap | Expected Result |
|---|---|---:|---:|---|
| UDP #1 | `ABCDEFGHIJKL` | 12 | 5 | `ABCDE`; last 7 bytes discarded |
| UDP #2 | `xyz` | 3 | 5 | `xyz` — a **new** datagram, not `FGHIJKL` |
| UDP #3 | `12345` | 5 | **3 explicitly set** | `123` |
| UDP #4 | `HELLO` | 5 | **5 restored** | `HELLO` |
| UDP #5 | `A🙂B` (UTF-8) | 6 | **3** | Hex `41 F0 9F`, Unicode cut mid-code point |
| UDP #6 | `abcde` | 5 | 5 | `abcde`, exact capacity match |
| NIO #1 | `NETWORK` | 7 | 4 | `NETW`, last 3 bytes discarded |
| NIO #2 | `ok` | 2 | 4 | `ok` — new datagram, not `ORK` |

There is no claim of proving Internet UDP delivery: if a firewall or environment blocks loopback UDP, the code will error or timeout. **A successful run on loopback demonstrates the semantics once a datagram is delivered**, not a promise that real networks will not drop or reorder packets.

## 6. Complete Java 17 Program — DatagramSocket and DatagramChannel

Create **`UdpSmallBufferDemo.java`** with the full code below. The program uses only Java SE 17:

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.charset.StandardCharsets;

public class UdpSmallBufferDemo {
    private static void require(boolean pass, String message) {
        if (!pass) {
            throw new AssertionError(message);
        }
    }

    private static void send(
            DatagramSocket sender, InetAddress host,
            int port, byte[] data) throws Exception {
        sender.send(new DatagramPacket(data, data.length, host, port));
    }

    private static void sendText(
            DatagramSocket sender, InetAddress host,
            int port, String text) throws Exception {
        send(sender, host, port,
                text.getBytes(StandardCharsets.US_ASCII));
    }

    private static String text(DatagramPacket packet) {
        return new String(packet.getData(), packet.getOffset(),
                packet.getLength(), StandardCharsets.US_ASCII);
    }

    private static String hex(DatagramPacket packet) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < packet.getLength(); i++) {
            int value = packet.getData()[packet.getOffset() + i] & 0xff;
            if (i != 0) {
                result.append(' ');
            }
            result.append(Character.forDigit(value >>> 4, 16));
            result.append(Character.forDigit(value & 15, 16));
        }
        return result.toString().toUpperCase(java.util.Locale.ROOT);
    }

    private static String receiveNio(
            DatagramChannel receiver, ByteBuffer buffer)
            throws Exception {
        buffer.clear();
        SocketAddress source = receiver.receive(buffer);
        require(source != null, "No UDP datagram");
        buffer.flip();
        byte[] data = new byte[buffer.remaining()];
        buffer.get(data);
        return new String(data, StandardCharsets.US_ASCII);
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        try (DatagramSocket receiver = new DatagramSocket(
                    new InetSocketAddress(loopback, 0));
             DatagramSocket sender = new DatagramSocket()) {
            receiver.setSoTimeout(2000);
            int port = receiver.getLocalPort();
            byte[] storage = new byte[5];
            DatagramPacket packet = new DatagramPacket(
                    storage, storage.length);

            sendText(sender, loopback, port, "ABCDEFGHIJKL");
            receiver.receive(packet);
            require(packet.getLength() == 5
                    && "ABCDE".equals(text(packet)), "First receive");
            System.out.println("UDP #1: " + text(packet)
                    + " (copied=" + packet.getLength() + " of 12)");

            packet.setLength(storage.length);
            sendText(sender, loopback, port, "xyz");
            receiver.receive(packet);
            require(packet.getLength() == 3
                    && "xyz".equals(text(packet)), "Second receive");
            System.out.println("UDP #2: " + text(packet)
                    + " (copied=" + packet.getLength() + ")");

            // Explicitly narrow the receive limit to three bytes.
            packet.setLength(3);
            sendText(sender, loopback, port, "12345");
            receiver.receive(packet);
            require(packet.getLength() == 3
                    && "123".equals(text(packet)), "Narrowed receive");
            System.out.println("UDP #3 with cap 3: "
                    + text(packet) + " (copied=" + packet.getLength() + ")");

            packet.setLength(storage.length);
            sendText(sender, loopback, port, "HELLO");
            receiver.receive(packet);
            require(packet.getLength() == 5
                    && "HELLO".equals(text(packet)), "Reset length");
            System.out.println("UDP #4 with cap 5: " + text(packet));

            byte[] unicode = "A\uD83D\uDE42B".getBytes(
                    StandardCharsets.UTF_8);
            require(unicode.length == 6, "UTF-8 payload length");
            packet.setLength(3);
            send(sender, loopback, port, unicode);
            receiver.receive(packet);
            require(packet.getLength() == 3
                    && "41 F0 9F".equals(hex(packet)), "UTF8 bytes");
            System.out.println("UDP #5 UTF-8 cut: "
                    + hex(packet) + " (sent=6, copied=3)");

            packet.setLength(storage.length);
            sendText(sender, loopback, port, "abcde");
            receiver.receive(packet);
            require("abcde".equals(text(packet)), "Exact-sized message");
            System.out.println("UDP #6 exact fit: "
                    + text(packet) + " (copied=" + packet.getLength() + ")");
            System.out.println("Length == capacity is ambiguous: "
                    + (packet.getLength() == storage.length));
        }

        try (DatagramChannel receiver = DatagramChannel.open(
                     StandardProtocolFamily.INET);
             DatagramChannel sender = DatagramChannel.open(
                     StandardProtocolFamily.INET)) {
            receiver.bind(new InetSocketAddress(loopback, 0));
            InetSocketAddress dest =
                    (InetSocketAddress) receiver.getLocalAddress();
            ByteBuffer small = ByteBuffer.allocate(4);

            int firstSent = sender.send(ByteBuffer.wrap(
                    "NETWORK".getBytes(StandardCharsets.US_ASCII)), dest);
            String first = receiveNio(receiver, small);
            require(firstSent == 7 && "NETW".equals(first), "NIO #1");
            System.out.println("NIO #1: " + first
                    + " (sent=7, copied=" + first.length() + ")");

            int nextSent = sender.send(ByteBuffer.wrap(
                    "ok".getBytes(StandardCharsets.US_ASCII)), dest);
            String second = receiveNio(receiver, small);
            require(nextSent == 2 && "ok".equals(second), "NIO #2");
            System.out.println("NIO #2: " + second
                    + " (copied=" + second.length() + ")");
        }
    }
}
```

### Compile and Run

On a machine with **JDK 17+** and loopback UDP allowed:

```bash
javac --release 17 -encoding UTF-8 UdpSmallBufferDemo.java
java UdpSmallBufferDemo
```

**Exact stdout of a successful run:**

```text
UDP #1: ABCDE (copied=5 of 12)
UDP #2: xyz (copied=3)
UDP #3 with cap 3: 123 (copied=3)
UDP #4 with cap 5: HELLO
UDP #5 UTF-8 cut: 41 F0 9F (sent=6, copied=3)
UDP #6 exact fit: abcde (copied=5)
Length == capacity is ambiguous: true
NIO #1: NETW (sent=7, copied=4)
NIO #2: ok (copied=2)
```

No fixed port appears in the output because the OS chooses an ephemeral port and the program does not print it. Each run may use a different port while preserving the output strings above if all local UDP datagrams are delivered successfully in the demo's send/receive order.

**Scope warning:** `DatagramChannel.receive` in this example uses **blocking mode**, so it does not have a dedicated `setSoTimeout` like `DatagramSocket`. Each `send` is called before `receive` in the same JVM to minimize blocking risk, though extreme environments could still drop a datagram. In real applications, use `Selector`/nonblocking mode and an appropriate deadline/cancellation mechanism to avoid hanging indefinitely.

## 7. Interpreting the Output: How Are Datagram Boundaries Preserved?

### UDP #1 — Large Datagram Truncated

The sender sends a 12-byte `DatagramPacket`, and the receiver allows at most 5 bytes. `receive` copies only `ABCDE`, with `getLength()==5`. The bytes `FGHIJKL` are discarded for **this receive turn**.

The key fact is not "5 bytes equals the buffer size," but that **we know the sent payload is 12 bytes in the test setup**, while the receiver only has 5 bytes. Never assume every full buffer indicates truncation.

### UDP #2 — Remainder of UDP #1 Is Not Received

The sender sends a **second datagram** containing `xyz`. The next `receive` gets `xyz`, not `FGHIJKL`. This demonstrates that a `DatagramSocket` does not behave like a TCP stream reader: **the datagram boundary is the unit of retrieval**.

### UDP #3 and #4 — `DatagramPacket.setLength` Changes the Receive Limit

The backing array is still `new byte[5]`. Before #3, the program sets `packet.setLength(3)`. When `12345` is sent, the packet only allows copying 3 bytes, so `123` is received.

Before #4, `packet.setLength(storage.length)` resets the limit to 5. Sending `HELLO` receives all 5 bytes. This shows that **array capacity is not synonymous with the packet's configured receive limit**, and `setLength` is how you explicitly specify how many bytes can be received in the next call.

Do not misinterpret #3 as a bug caused by automatically reusing `getLength()` after #2: in #3 we **explicitly narrowed** the cap. Without reading the source/Javadoc and testing, guessing about reuse behavior across JDKs/platforms can lead to wrong explanations.

### UDP #5 — Cut Mid-UTF-8 Character

The sender encodes the text `A🙂B` in UTF-8:

```text
41          : "A"       (1 byte)
F0 9F 99 82 : "🙂"      (4 bytes)
42          : "B"       (1 byte)
Total       : 6 bytes
```

The receiver accepts at most 3 bytes:

```text
41 F0 9F
```

This is **not a complete UTF-8 string**: it has the first and second bytes of the emoji but is missing the rest. If decoded with a replacing decoder, you might see `�` or corrupted content; if configured to report errors, the decoder will reject the malformed input. **Byte-level length and content validation must happen before parsing text/JSON**, because Java's `String.length()` is not the UTF-8 byte count.

Do not assume that `new String(received, UTF_8)` not throwing an exception means the message is intact. That overload typically replaces malformed sequences according to its decoder policy. When strictness is required, use `CharsetDecoder` with `CodingErrorAction.REPORT` and handle `CharacterCodingException`.

### UDP #6 — A Full Buffer Does Not Prove Truncation

Exactly **5 bytes** `abcde` were sent into a 5-byte receive buffer, yielding `getLength()==5` — **no truncation**. Compare with #1, which also had `getLength()==5` but **was truncated**:

| Case | Sender Payload | Receiver Cap | `getLength()` | Truncated? |
|---|---:|---:|---:|---|
| #1 | 12 | 5 | 5 | **Yes** (known from sender-side experiment) |
| #6 | 5 | 5 | 5 | **No** |
| Observing only receiver `length == cap` | **Unknown** | 5 | 5 | **Cannot be determined** |

A high-level receive API like `DatagramSocket.receive` does not return an "original payload length" or an independent truncation flag. Therefore, **`received.getLength()==buffer.length` is a warning signal, not proof of truncation**. If you need to know a datagram is intact, design framing/expected-length into the payload, size buffers for the maximum contracted payload, and validate the entire record.

### NIO #1 and #2 — ByteBuffer Also Preserves Datagram Boundaries

`DatagramChannel.receive(ByteBuffer)` places received bytes into the available space (`remaining()`) of a `ByteBuffer`. With a 4-byte buffer and the 7-byte `NETWORK`, `NETW` is received; the 3 bytes `ORK` are discarded.

Next, after `buffer.clear()`, the sender sends another datagram `ok` and the receiver gets `ok`. No `ORK` bytes are waiting to be read. `clear()` only resets the **application buffer's** position/limit; it **does not** recover lost UDP data.

## 8. `DatagramChannel`, ByteBuffer, and the Position/Limit Issue

`DatagramChannel` in NIO supports sending/receiving UDP with `ByteBuffer` instead of `DatagramPacket`. Key differences to know:

- `DatagramChannel.receive(dst)` returns the `SocketAddress` of the received datagram; when configured nonblocking and no datagram is ready, it can return `null`.
- It copies data into `dst` starting at the **current position**; the available space is `dst.remaining()`, **not simply `dst.capacity()`**.
- After receiving, `position` advances by the number of bytes copied, and `limit` is unchanged. Call `flip()` to switch to reading the newly received bytes.
- Before a new receive, call `clear()` to set `position=0` and `limit=capacity`; if you want to grant only a subset, adjust `limit` intentionally.
- If the buffer is too small, the remaining bytes of the datagram **are silently discarded**. The API does not report the original datagram length.
- If `dst` is read-only, `receive` can throw `IllegalArgumentException`; a writable buffer is required.
- For a **connected** channel, `read(ByteBuffer)` reads **one datagram from the connected peer**; it still does not turn it into a TCP stream.

### Illustrating "Large Capacity but Small Remaining"

```java
// Illustrative code; channel is an open DatagramChannel.
ByteBuffer buffer = ByteBuffer.allocate(1024);
buffer.position(1020);  // 4 bytes remaining from position to limit

SocketAddress peer = channel.receive(buffer);
// If a 100-byte datagram is delivered, only 4 bytes of space remain;
// the excess bytes are discarded, even though capacity() is 1024.
```

Do not guess the receive capacity from `capacity()` when `position` is non-zero. In the demo, the `receiveNio` helper always calls `clear()` before receiving and `flip()` after receiving, so the readable bytes match the exact received region.

### `ByteBuffer.flip` and `clear` Do Not Touch the Network

These two methods only update the buffer's read/write boundary metadata; they do not send an `ACK`, trigger UDP retransmission, or modify kernel buffers. `clear()` also does not zero out the underlying byte array; it only allows overwriting. If sensitive data is stored, apply a separate security/zeroization policy.

### Nonblocking Mode Requires a Selector/Deadline

With `channel.configureBlocking(false)`, `receive` can return `null` immediately when no data is available. A production application can use `Selector` with `SelectionKey.OP_READ`, checking timeouts and cancellation; do not write a CPU-burning `while (receive()==null) {}` spin loop. With a blocking channel, ensure proper lifecycle/close/cancellation handling if the peer goes silent.

## 9. Distinguishing Application-Buffer Truncation from OS and Network Loss

There are three distinct scenarios:

### A. Datagram Arrived, Application Buffer Too Small

- The receiver's `receive` call succeeds.
- `DatagramPacket` or `ByteBuffer` receives the leading portion up to its limit.
- The remainder of **that datagram** is discarded during the receive step.
- There is no automatic retransmission or retrieval of the remainder via subsequent `receive` calls.

This is what the **main loopback experiment** verifies.

### B. Socket/OS Receive Queue Full

If the receiver does not read fast enough, the receive queue can fill up and new datagrams are dropped before the application ever sees them. `SO_RCVBUF` / `DatagramSocket.setReceiveBufferSize` influences kernel buffer/queue sizing subject to OS mechanisms and limits; it **does not fix a 5-byte packet trying to receive a 12-byte datagram**.

On Linux, you can inspect UDP error/drop counters using appropriate OS tools; counter names and tools differ across Linux, Windows, and macOS. Do not blame "truncation" for a missing packet that may have been **dropped at the socket queue**.

### C. IP Fragmentation, MTU, or In-Transit Datagram Loss

A UDP datagram exceeding the path MTU may require IP fragmentation or be rejected, depending on IP version, DF/PMTU, and the network stack. If an IP fragment is lost, **the entire UDP datagram may never be delivered to the socket** after reassembly. This is a network-layer issue distinct from **application receive buffer truncation**.

A sender's successful `send` call only confirms the socket/API send operation per its contract; it does not prove the receiver got the full datagram or that the application processed it successfully. There is no built-in automatic UDP ACK acting as a business protocol.

## 10. MTU, Datagram Length, and Choosing Sizes

The UDP header is **8 bytes**. For IPv4 without options, the IP header is typically **20 bytes**; thus, the UDP payload must account for IP/UDP overhead within the IP packet size. The theoretical limit for a UDP payload in basic IPv4 is **65,507 bytes** (65,535 − 20 − 8), but **you should not approach that maximum on the Internet**. IPv6, extension headers, links, tunnels, VPNs, and firewalls impose further limits.

For example, on a network path with a **1,500-byte** MTU, a 20-byte IPv4 header, and an 8-byte UDP header, an unfragmented datagram simply needs a payload of at most about **1,472 bytes**. This is **not a guaranteed number across the Internet**: VPNs/tunnels add overhead, and IP options or actual PMTU can vary. Practical design should be based on requirements and measuring path/PMTU or choosing a conservative size validated in the target deployment environment.

**Do not confuse two things:**

- **MTU/fragmentation:** Does the datagram reach the socket intact across the network?
- **Application receive buffer:** Once the datagram arrives, does `receive` have enough space to copy the **entire payload**?

Even a 64-byte datagram, with no MTU issues, will still **be truncated at the API** if you receive it into a 5-byte buffer.

### What to Do When Payloads Are Large?

- Reduce the size **per datagram** or split the data into multiple **logical messages/datagrams according to your own protocol**.
- If application-layer fragmentation is needed, each fragment must include **message ID, sequence/part index, total count/total bytes, checksum/integrity, deadline**, and a bounded reassembly mechanism.
- Enforce limits on fragment count, total bytes, in-flight messages, timeouts, duplicate policy, authentication, and resource exhaustion protection.
- For large data requiring **complete, ordered, reliable** delivery, consider TCP/TLS or a suitable reliable protocol; raw UDP does not provide these guarantees on its own.
- Do not set a huge `SO_RCVBUF` to mask a design that sends arbitrarily large datagrams.

### Effect of Checksums

UDP/IP has checksums/error checks at appropriate layers, but checksums only help detect certain types of in-transit corruption; **they do not guarantee datagram delivery, prevent replay/injection, ensure the application buffer is large enough**, or replace protocol authentication.

## 11. To Detect Truncation, Define "Complete Data" in the Protocol

A received datagram whose length equals the buffer cap has **two possibilities**:

1. The datagram was exactly cap bytes long and arrived complete.
2. The datagram was longer than cap and was truncated.

`DatagramPacket.getLength()` cannot distinguish these two cases on its own. Hence, an **application-level record format** and validation are required.

Example of a custom message format:

```text
+------------+----------+----------+-------------------------+
| version(1) | type(1)  | len(2)   | payload(len bytes)      |
+------------+----------+----------+-------------------------+
              network byte order for length
```

When receiving, you should:

1. Check that the buffer has at least the **4-byte header**; otherwise reject.
2. Parse `len` as an unsigned 16-bit integer in the specified byte order.
3. Compare `len` against **maxAllowedPayload** and the expected total datagram length.
4. Check `actualReceivedBytes == 4 + len` (if the protocol requires a single record per datagram).
5. Decode/parse the payload only after validating framing and required fields.
6. If bytes are missing or oversized, **drop the record and record a metric**; do not append a subsequent datagram to the current record if the protocol has no fragmentation design.
7. Authenticate the content and sender according to your threat model; the `len` field declared by the sender is still **untrusted input** that could be wrong or forged.

This is a **protocol illustration**, not a standard format provided by Java. If a malicious sender declares a length matching the truncated portion, a single check still cannot catch all tampering; message authentication or checksums/sequences are needed depending on the goal.

### Sample Application-Side Length Validation

```java
// Illustrative; 4-byte header, n is the actual bytes received.
// Proceed only if the entire datagram is authenticated and schema-valid.
if (n < 4) {
    throw new IllegalArgumentException("Datagram header too short");
}

int payloadLength =
        ((data[offset + 2] & 0xff) << 8)
        | (data[offset + 3] & 0xff);

if (payloadLength > maxPayload
        || n != 4 + payloadLength) {
    throw new IllegalArgumentException("Truncated/invalid datagram");
}
```

In a real protocol design, also validate offset bounds, version/type, authentication, checksum, source identity, and total quotas. `n` must be the **actual number of bytes received**, not `array.length`. Never allocate a 65 KiB array (or more at the reassembly layer) simply because an unvalidated `length` field requested it.

## 12. UTF-8, Strings, and Bytes: Never Use Character Count as Receive Capacity

UDP sends **byte arrays**, not raw Java Strings. A Unicode string can have fewer code units than bytes:

```text
Java String: "A🙂B"
UTF-16 code units = 4   // A=1, emoji=2, B=1
UTF-8 bytes       = 6   // 41 F0 9F 99 82 42
```

Therefore, **`String.length()` is not the size to send or receive over UDP**. Correct:

```java
byte[] payload = message.getBytes(StandardCharsets.UTF_8);
DatagramPacket outbound = new DatagramPacket(
        payload, payload.length, receiverAddress, receiverPort);
sender.send(outbound);
```

If you receive into a buffer smaller than `payload.length`, you can lose the trailing bytes of a code point. Calling `new String(received, UTF_8)` may replace the broken bytes and produce text that looks "almost right"; this is dangerous for JSON, signatures, hashes, and protocol framing.

**Recommendations:**
- For text protocols, decode UTF-8 **after** verifying the datagram is complete and structurally valid.
- When strict decoding is needed, use `CharsetDecoder` with `onMalformedInput(CodingErrorAction.REPORT)` and `onUnmappableCharacter(CodingErrorAction.REPORT)`.
- For binary protocols, keep data as `byte[]`/`ByteBuffer`; do not convert to `String` and back to bytes.
- Do not confuse a UTF-8 split across **two UDP datagrams** with TCP's UTF-8 streaming: if the application intentionally splits a message across multiple datagrams, it must perform sequence/order reassembly and handle loss/reordering/duplicates before decoding.

## 13. Timeouts, Resource Closing, and Experiment Stability

### `DatagramSocket.setSoTimeout`

The receiver in the demo calls:

```java
receiver.setSoTimeout(2000);
```

This limits how long `DatagramSocket.receive` waits when no datagram arrives. If it expires, the method throws `SocketTimeoutException`; **it does not prove the sender failed to send** or that the datagram is not on the network—it only indicates `receive` did not receive a datagram within the timeout per the API.

A socket timeout is not a signal that "the remainder of datagram #1 has finished," because UDP has no mechanism to request the remainder. If the peer sends no new datagram, the next `receive` may wait until timeout.

### `DatagramChannel` Needs Its Own Timeout Strategy

In the NIO example, `DatagramChannel` is blocking by default; we use `try-with-resources` and send before receiving on loopback. For long-running services, use nonblocking mode + `Selector` with a deadline, or a channel cancellation/close mechanism. Do not apply `setSoTimeout` to a `DatagramChannel` and expect all blocking channel reads to share the same semantics; channel/selector integration differs from the traditional Socket API.

### Cleanup

Both `DatagramSocket` and `DatagramChannel` are closeable, so use `try-with-resources`:

```java
try (DatagramSocket socket = new DatagramSocket()) {
    // send/receive UDP
}
```

Do not use `Thread.sleep` to fake synchronization in tests. The program above sends one packet, receives it, and runs assertions; this simplifies testing but does not prevent all scheduling or OS drop issues. In CI, verify that the environment allows loopback UDP, set appropriate deadlines, and handle timeouts with clear error messages.

### Observing with Packet Capture

In a test environment where Wireshark/tcpdump is permitted and packet capture is approved:

1. Filter UDP traffic on loopback and the actual ephemeral port.
2. Observe that the **on-the-wire payload length** of datagram #1 is 12.
3. Compare it against the **5** bytes reported by the application.
4. Observe datagram #2 is `xyz`; there is no new datagram carrying the `FGHIJKL` remainder.
5. This distinguishes **the network delivered the full datagram** from **the application buffer truncated it**.
6. If the capture shows no datagram or shows fragmentation on a real network, reclassify it as a delivery/fragmentation/OS queue issue.

Do not use captures containing real data or credentials without an appropriate retention policy and access permissions.

## 14. Common Mistakes When Sending and Receiving UDP with Small Buffers

| Mistake | Why It Is Wrong | Correct Approach |
|---|---|---|
| "Receive 5 bytes, then receive again for the remaining 7 bytes" | UDP has datagram boundaries; the remainder is discarded | Send datagrams fitting the cap; use protocol reassembly if intentionally split |
| Treating UDP like a TCP stream | TCP does not preserve application message boundaries; UDP does | Parse each datagram as a unit; do not arbitrarily concatenate them |
| `new String(packet.getData())` | Reads the entire backing array, including stale/unrelated bytes | Use `offset` and `getLength()` |
| Counting `String.length` to size a byte buffer | UTF-8 byte length differs from UTF-16 char count | Compute `getBytes(UTF_8).length` or protocol max |
| Assuming `getLength()==cap` guarantees truncation | The datagram may have been exactly `cap` bytes | Validate expected payload/schema length |
| Assuming `getLength()<cap` proves everything is valid | The packet can still fail schema checks or miss logical chunks | Validate the protocol message |
| Treating `SO_RCVBUF` as the `DatagramPacket` cap | The kernel receive queue is separate from the Java array | Distinguish OS queue from application buffer |
| Thinking increasing `SO_RCVBUF` recovers truncated bytes | Excess bytes of an already-received datagram cannot be recovered | Fix the application receive cap/protocol |
| Treating `ByteBuffer.capacity` as receivable byte count | `remaining = limit - position` is the actual space | Call `clear()` or set `limit` properly before receiving |
| Forgetting `flip()` before reading a received `ByteBuffer` | `position` is at the end of the write; reads empty/wrong data | Call `flip()` then read `remaining` |
| Calling `clear()` to recover lost UDP bytes | `clear()` only resets buffer metadata | Retransmit at the app protocol level if needed |
| Assuming payloads > MTU always arrive intact | Fragmentation/drops/firewalls/PMTU | Control datagram size and network path |
| Thinking `send()` returning means the receiver processed it | UDP has no application ACK | Use ACKs/sequences/checksums/retries in the protocol |
| Omitting timeouts on `receive` | The app can block forever if a datagram is lost | Use `setSoTimeout`/Selector/deadline |
| Concluding the Internet is reliable from a loopback test | Loopback removes network variables | Test loss/reordering/duplicates/MTU outside the lab |
| Arbitrarily concatenating JSON from two UDP packets | No ordering or length guarantees | Message IDs, fragments, reassembly, validation |
| Decoding UTF-8 immediately when buffer is full | May cut mid-code point | Validate bytes; use a strict decoder when needed |
| Trusting an unauthenticated payload length | Can cause wrong allocation/parsing or DoS | Quotas, bounds checks, and authentication |
| Sharing a buffer across async receives without copying | Data can be overwritten by the next packet | Clear ownership; copy before async processing |
| Using a `DatagramPacket` concurrently from multiple threads | Mutable packet state causes races | Per-operation state or designed synchronization |
| Concluding bytes were truncated just from a "short" receive | The sent datagram may actually be short or lost elsewhere | Cross-check sender/test fixture/capture/protocol |

## 15. Follow-up Exercises After Running the Demo

### Exercise A — Changing the Receive Cap

Keep the sender sending `ABCDEFGHIJKL`, change the backing buffer from 5 to 8 bytes, and predict:

- What does Datagram #1 receive?
- What is `getLength()`?
- Is the next `receive` the remainder `IJKL`?
- If an exact 8-byte datagram is sent, does `getLength()==8` distinguish "complete" from "truncated"?

**Expected:** the first 8 bytes `ABCDEFGH` are received, the remainder is discarded; the next `receive` still gets a different datagram. `getLength()==8` remains ambiguous without knowing the sender's payload.

### Exercise B — Two Independent Short Datagrams

Send `AA` and `BBB` sequentially to a receiver with a 100-byte buffer. Perform two `receive` calls and count the bytes each time. Why is a single `AABBB` string not received as in a TCP stream?

**Expected:** two `receive` calls, each returning one datagram of length 2 and 3 bytes (when delivered), not merged into 5 bytes in a single call.

### Exercise C — NIO Position

Change `ByteBuffer.allocate(4)` to `ByteBuffer.allocate(8)` and set `position(6)` right before `receive`. Send `NETWORK`. How much space is available?

**Expected:** `remaining()=2`, copying `NE` and discarding `TWORK`. To receive all 7 bytes, at least 7 bytes of remaining space are needed and `flip()` must be called before reading. When repeating the experiment, be sure to manage `position`/`limit` before receiving.

### Exercise D — UTF-8 Boundary

Keep the payload `A🙂B`, and test caps of 1, 2, 3, 5, and 6 bytes. Print hex and use a strict decoder. At which cap does the datagram fit the entire payload?

**Expected:** 6 bytes are required; caps of 2 or 3 cut mid-emoji, and a cap of 5 holds `A`+emoji but misses `B`. "Successfully decoding a valid string" does not mean the full business-protocol payload was received.

### Exercise E — Receiving with a Payload Length Header

Create a datagram with a 2-byte big-endian payload length + text payload. Have the receiver always read up to the contract max size and validate `actualLength == 2 + declaredLength`. Send valid payloads, payloads exceeding the cap, and forged length fields.

**Expected:** datagrams violating the schema are rejected **before parsing business data**. Never trust `declaredLength` for unbounded allocation.

### Exercise F — Loss and Reordering

Extend the sender to send datagrams with a `sequenceNumber`, then intentionally drop or reorder sends in the test harness. The receiver must detect missing/duplicate/out-of-order packets without assuming datagram boundaries guarantee ordering or reliability.

**Expected:** design your own application protocol, timeout/reassembly, and error metrics; never promise UDP will retransmit on its own.

## 16. Self-Check Questions

**Q1.** Send a 100-byte UDP datagram with a 10-byte `DatagramPacket` receive cap. After `receive`, does calling `receive` again retrieve the remaining 90 bytes?

**Answer:** No. Once the datagram is received with a cap of 10, the remainder is discarded. The next `receive` waits for another datagram.

**Q2.** Why does UDP differ from TCP regarding splitting data across reads?

**Answer:** UDP is datagram/message-oriented and preserves datagram boundaries at the receive API; TCP is a byte stream and does not preserve application message boundaries.

**Q3.** Does `DatagramPacket.getLength()==buffer.length` prove the datagram was truncated?

**Answer:** No. It could also be a datagram whose length exactly matches the buffer. You must know the sender's size or validate application framing.

**Q4.** Why can `new String(packet.getData(), UTF_8)` be wrong?

**Answer:** Because it reads the entire backing array instead of the exact `offset` and received byte count. It can also decode incorrectly if UTF-8 was cut mid-code point.

**Q5.** Does `setReceiveBufferSize(65535)` allow a `new byte[5]` array to receive all 12 bytes?

**Answer:** No. `SO_RCVBUF` is a socket/kernel receive queue hint; the application's array/packet receive length is still only 5 bytes.

**Q6.** How many UTF-8 bytes are needed to send `"A🙂B"`?

**Answer:** 6 bytes: `41 F0 9F 99 82 42`. Java's `String.length()` is 4 UTF-16 code units, not 6 bytes.

**Q7.** With `ByteBuffer.allocate(10)` but `position=8, limit=10`, how many bytes at most can be received?

**Answer:** 2 bytes. `remaining()=2`; actual capacity depends on `remaining`, not `capacity`.

**Q8.** Does `ByteBuffer.clear()` recover the truncated portion of a datagram?

**Answer:** No. It only resets buffer metadata for the next read/write.

**Q9.** When `DatagramChannel.configureBlocking(false)` is set, does `receive` returning `null` mean the previous datagram was truncated?

**Answer:** No. It indicates no datagram is currently available at the time of the call; it is unrelated to any remainder of a previous datagram.

**Q10.** Does `DatagramSocket.setSoTimeout(2000)` guarantee the sender will send within 2 seconds?

**Answer:** No. It limits how long a blocking `receive` waits, throwing `SocketTimeoutException` upon expiration.

**Q11.** You see a 12-byte datagram in a packet capture, yet Java only receives 5 bytes. Which layers should you check?

**Answer:** Specifically the application receive buffer cap/offset/`DatagramPacket` length or `ByteBuffer` remaining. Separate this from earlier kernel queue drops and IP fragmentation.

**Q12.** When sending a datagram larger than the path MTU, will the receiver definitely get two separate application datagrams?

**Answer:** No. IP fragmentation/reassembly does not turn one UDP datagram into two UDP application datagrams. If a fragment is lost, the entire UDP datagram may fail to be delivered.

**Q13.** What is needed to send a large document completely and in order over UDP?

**Answer:** Application-level segmentation, sequence/IDs, bounded reassembly, integrity checks, timeouts, retransmission/ACKs, and security; or choose an existing reliable protocol.

**Q14.** Calling `receive` returns only 3 bytes `xyz` even though the buffer is 100 bytes; were 97 bytes lost?

**Answer:** No. That datagram may simply be 3 bytes long. The buffer size is a **maximum capacity**, not a mandatory byte count to receive.

**Q15.** When reusing a packet after a short receive, should you assume the next receive cap is always the previous `getLength()`?

**Answer:** No. Explicitly call `setLength` to the intended capacity or create a new packet, relying on the API and testing rather than inferring implementation details from previous received byte counts.

## 17. Post-Lab Implementation Checklist

Before deploying UDP networking in Java 17:

1. **Define max payload per datagram** based on the protocol, network, and MTU/PMTU to support.
2. **Allocate receive buffers large enough** for the maximum valid datagram, not just typical text.
3. **Distinguish receive cap from `SO_RCVBUF`**; increasing the OS queue does not fix a small packet/`ByteBuffer`.
4. **Use `DatagramPacket.getOffset()` and `getLength()` properly**; do not parse the entire backing array.
5. **If reusing packets**, explicitly call `setLength` for the allowed free space to avoid unintended caps.
6. **If using NIO**, check `remaining()`, call `clear()` before receiving, and `flip()` before reading.
7. **Do not expect a second receive to fetch the remainder of the first**; one call consumes one datagram.
8. **Do not use `length==capacity` as proof of truncation**; design framing/length/checksum/schema validation.
9. **Count sizes in bytes**; for UTF-8 Unicode, validate byte integrity before decoding.
10. **Set timeouts/deadlines** to avoid infinite blocking when packets are lost; do not confuse timeout with EOF or truncation.
11. **Handle UDP loss/reordering/duplicates** if business logic requires it; do not equate a successful send with delivery.
12. **Bound reassembly/quotas** if splitting large messages across datagrams to prevent DoS/memory exhaustion.
13. **Use try-with-resources** and never carelessly share mutable receive buffers across threads.
14. **Test on both loopback and real networks**, distinguishing application truncation, socket drops, MTU fragmentation, and firewalls.
15. **Add layer-appropriate metrics/logs**: `bytesCopied`, `expectedLength`, `datagramCount`, `malformedPackets`, timeouts, and drops/reordering where observable.

**Remember:** UDP is received **datagram by datagram**. If a datagram is larger than the receive buffer, the excess **is discarded**, not queued for the next `receive` call. `DatagramPacket.getLength()` and `ByteBuffer.remaining()` report the limits and byte counts observed in Java, but **do not by themselves provide proof of an intact datagram when the buffer is full**. Experimenting with small buffers demonstrates why proper sizing, framing, byte-level validation, and protocol design are essential.

### Official References

- [Java SE 17 — DatagramSocket: receive, send, setSoTimeout, SO_RCVBUF](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html)
- [Java SE 17 — DatagramPacket: getLength, getOffset, setLength](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramPacket.html)
- [Java SE 17 — DatagramChannel: receive(ByteBuffer) and remainder discarded](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [Java SE 17 — ByteBuffer: position, limit, remaining, flip, clear](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 17 — CharsetDecoder and CodingErrorAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [RFC 768 — User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768)
- [RFC 8085 — UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085)