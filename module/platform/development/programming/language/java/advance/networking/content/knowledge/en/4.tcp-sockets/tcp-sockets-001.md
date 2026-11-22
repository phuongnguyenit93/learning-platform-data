# TCP Provides an Ordered Byte Stream; Limits of Transport Guarantees

**Context:** Java Networking — TCP communication via `Socket` and `ServerSocket`. An application may call `write()` twice, and the receiving side may call `read()` three times, yet still receive the exact **same sequence of bytes in the exact same order**. That is the core property of TCP; the number of calls, message boundaries, and whether the business logic has processed the data successfully are separate concerns.

After this lesson, you should be able to distinguish between (1) the ordering and reliability of a **byte stream** versus **message** boundaries, (2) the result of `Socket` I/O versus whether the operating system or remote application has received/processed the data, and (3) transport-level error detection mechanisms versus business-level confirmation mechanisms.

## 1. The TCP Model: One Connection, Two Ordered Byte Streams

TCP (Transmission Control Protocol) operates over IP and provides a logical connection between two endpoints. Within an established connection, application data is treated as a **continuous sequence of bytes**, not as records or packets with business meaning. The connection is **full-duplex**: each direction has its own byte stream, ordering, and send-side close state.

```text
Application A                              Application B
OutputStream A ──[byte 0,1,2,3,...]──> InputStream B
 InputStream A <──[byte 0,1,2,3,...]── OutputStream B
       |                                           |
     TCP A ======= IP (may drop/reorder) ======= TCP B
```

An application reading from `InputStream` will observe bytes delivered **in the exact order they were sent in the same direction of the same connection**, provided those bytes are actually delivered to the application before the connection errors out or closes. Internally, TCP may split a single write into multiple segments, coalesce writes, retransmit lost segments, and receive out-of-order segments, then reassemble them before handing bytes to the application.

For example, sending `ABCDEF` might be split by the application into `write("ABC")` and `write("DEF")`. The receiving side might read `AB`, `CD`, `EF`; or `A`, `BCDE`, `F`; or all of it in a single sufficiently large `read`. **The final byte sequence is still `ABCDEF`.** All such splits are valid; do not equate `read` or `write` boundaries with message boundaries.

TCP sequence numbers identify the position of bytes in the stream; a segment is TCP's unit of transport, whereas the `read` method simply retrieves the number of bytes currently available according to stream rules. There is no one-to-one mapping between **Java calls**, **TCP segments**, and **application messages**.

## 2. What Does TCP Guarantee, and by What Mechanisms?

Under normal operating conditions of a connection, TCP aims to deliver a byte stream that is **ordered, free of duplicate bytes, and free of silent byte loss** to the application. The main mechanisms are:

1. **Sequence numbers:** locate bytes within the stream. If segments arrive out of order, the receiver can buffer later bytes to reassemble the correct order before delivering them to the application.
2. **ACKs and retransmission:** the receiver acknowledges reception progress; the sender can retransmit unacknowledged data when packet loss is detected. Duplicate arriving segments do not cause the application to see duplicated bytes in the same stream.
3. **Checksums:** help detect many data transmission errors at the transport layer. This is not cryptographic protection against intentional tampering and does not replace TLS or application-layer integrity checks.
4. **Flow control:** the receive window reflects the receiver's buffer capacity; the sender cannot keep sending indefinitely beyond the receiver's capacity.
5. **Congestion control:** adjusts the sending rate according to network conditions, reducing congestion risk; this can cause latency and throughput to vary.

An important point about the term **reliable**: TCP attempts to **recover from packet loss while the connection remains viable** or eventually report a connection failure. It **does not guarantee that every byte will reach the destination within a bounded time**, does not turn a broken connection into an unbroken one, and does not provide "exactly-once" business transactions.

**Ordered delivery** also has a trade-off: if an earlier byte is lost, later bytes may already sit in the buffer yet cannot be delivered in order to the application; this is the *head-of-line blocking* phenomenon within a single TCP stream.

## 3. Guarantee Boundaries: TCP Is Neither a Message Protocol Nor a Business Confirmation

| Common misconception | What TCP/Java actually states |
| --- | --- |
| `write(bytes)` returns without error | Java has completed the stream write call per its interface; **does not prove** the remote application processed it or that data is durably persisted |
| A TCP ACK has been sent back | The peer TCP stack acknowledged the stream bytes per protocol; **not** an application-logic ACK |
| One `write` equals one message | TCP does not preserve write boundaries; the reader may split/coalesce depending on timing and buffers |
| `read(buffer)` fills the entire buffer | Usually returns only **a positive byte count ≤ requested size**; a loop is required when more bytes are needed |
| The TCP connection has `isConnected() == true` | Was connected successfully at one point; does not prove the peer is currently alive or that future data will be delivered |
| TCP "guarantees ordering" | Only **within one direction of a specific connection**; does not order across different connections or independent requests |
| TCP guarantees "exactly once" | Eliminates duplicate bytes within a live stream; **does not** deduplicate business commands when the application resends after a disconnect |
| TCP automatically encrypts/authenticates | TCP does not do this; the application needs TLS and appropriate authentication mechanisms |

Three layers of confirmation must be clearly separated:

```text
Client calls write()
  → data enters client send path/buffer
    → peer TCP receives and ACKs data
      → peer application reads/decodes request
        → peer application executes and commits result
          → peer sends application ACK/response
```

Milestones on the right cannot be inferred from milestones on the left. Even when the client has received a response, you still need to explicitly define **whether the response is sent before or after commit** if you want to use it to confirm durable success.

When a connection fails at an ambiguous moment, the data may have already reached the server and been committed even though the client never saw the response. Resending the same command on a new connection risks **executing twice** if the protocol does not support idempotency/deduplication keys.

## 4. Reading/Writing via `java.net.Socket`: Seeing the API Semantics Correctly

A `ServerSocket` listens, and `accept()` returns a connected `Socket`. Each `Socket` has an `InputStream` for reading the incoming byte stream and an `OutputStream` for writing the outgoing byte stream.

Illustrative snippet (variables `socket` and `payload` are assumed declared in program context, not a standalone example):

```java
socket.getOutputStream().write(payload); // Does not create a message boundary.
byte[] buffer = new byte[4096];
int n = socket.getInputStream().read(buffer);

// n is the number of bytes actually read; -1 indicates EOF.
// If n > 0, only buffer[0..n) contains the newly read data.
```

### `InputStream.read` may return fewer bytes than requested

When reading up to 4096 bytes, `read(buffer)` **does not promise** to return 4096 bytes. On a normal blocking stream, it may return a smaller positive number of bytes even when the peer is still sending more; `-1` signals EOF when no more data remains and the sender has closed the stream cleanly. Calling `read(buffer, off, 0)` is allowed to return `0` because a zero-length read was requested. In a typical loop using a non-empty buffer, handle `-1` and the read byte count separately.

Do not use `InputStream.available()` to query **the length of an entire message**: per the API contract, it is only an estimate of bytes that can be read immediately without blocking, not the total bytes of a request or upcoming data.

### `OutputStream.write` does not mean "the peer has received it"

A `write` call may copy bytes into the send buffer system and return before the peer receives them. Conversely, if the send buffer is full or the network is slow, the write call may block. `flush()` on `BufferedOutputStream` pushes bytes currently held in the Java buffer down to the underlying stream; it **does not create a TCP record**, does not inherently wait for the remote application to read, and is not equivalent to an application ACK. On a raw socket output stream, you should not infer that `flush()` means "confirmed on the other end."

For text strings, always specify the charset explicitly (typically UTF-8) **after assembling all bytes of a message**: a UTF-8 character can be split across two reads. Do not decode each byte chunk into a `String` and assume no characters are corrupted at the cut point.

## 5. Java 17+ Example: Two Writes, Without Reading by Write Boundaries

This example uses loopback and an OS-assigned port (port `0`), running in the same JVM. It deliberately uses a 2-byte buffer to show the loop needed to assemble multiple chunks; **the actual number of `read` calls is not a stable result to assert in tests**.

Save as **`TcpStreamChunks.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpStreamChunks {
    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress());
             Socket writer = new Socket(
                InetAddress.getLoopbackAddress(), listener.getLocalPort());
             Socket reader = listener.accept()) {

            OutputStream out = writer.getOutputStream();
            out.write("ABC".getBytes(StandardCharsets.UTF_8));
            out.write("DEF".getBytes(StandardCharsets.UTF_8));
            writer.shutdownOutput();

            InputStream in = reader.getInputStream();
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            byte[] buffer = new byte[2];
            int n;
            while ((n = in.read(buffer)) != -1) {
                bytes.write(buffer, 0, n);
            }

            System.out.println(new String(
                    bytes.toByteArray(), StandardCharsets.UTF_8));
        }
    }
}
```

Compile/run with JDK 17+:

```sh
javac -encoding UTF-8 TcpStreamChunks.java
java TcpStreamChunks
```

Deterministic stdout:

```text
ABCDEF
```

On the sending side there are two write calls (`ABC`, `DEF`). The receiving side uses a 2-byte buffer so it may take multiple reads, yet assembling them in order yields `ABCDEF`. The code does not check "exactly how many bytes the first read returned," because that is a timing/buffering detail, not part of the TCP contract.

`writer.shutdownOutput()` signals the end of **the client's send direction**: only after reading all bytes before the FIN does the receiver observe `read() == -1` and exit the loop. This demo assembles until EOF within a single connection that sends one payload and then half-closes; **you cannot copy the "read until EOF" technique directly into a protocol that keeps the connection open to send multiple consecutive messages**. `ByteArrayOutputStream` also grows with the data, making it unsuitable for receiving unbounded data from an untrusted peer.

## 6. How Do You Know When a Message Ends? Application-Layer Framing Is Required

Because TCP does not carry message boundaries, you must **define framing** before decoding data or moving on to process the next request. Three common options:

| Framing | How the end is detected | Conditions/risks to handle |
| --- | --- | --- |
| **Length-prefix** | Header carries payload length, followed by that exact number of bytes | Size limits, endianness, negative/overflow length, premature EOF |
| **Delimiter** (`\n`, CRLF, separator character) | Read until the terminating marker | Escaping delimiters in payload, line length limits, charset |
| **Until EOF** | Read until the peer closes its send direction | Only usable when the protocol specifies one body until close; unsuitable for exchanging multiple messages in the same direction on an open connection |

Minimal framing example using a **4-byte big-endian integer** and a UTF-8 payload:

```text
+------------------------+-------------------------------------+
| 4 byte length = N      | N byte payload (UTF-8)             |
+------------------------+-------------------------------------+
| readInt()              | readFully(byte[N])                 |
+------------------------+-------------------------------------+
```

If two consecutive frames are sent, the receiver repeats **read header → validate length → read full N bytes → process frame**. In Java, `DataOutputStream.writeInt` and `DataInputStream.readInt` agree on integer representation; `DataInputStream.readFully` attempts to read the full number of bytes or throws `EOFException` if the stream ends prematurely. Never allocate an array from a peer-supplied length without validating reasonable bounds first.

The length must be computed in **encoded bytes**, for example `payload.getBytes(StandardCharsets.UTF_8).length`, not the character count in `String.length()`. A Vietnamese character usually takes more than one byte in UTF-8.

## 7. Complete Java 17+ Example: Framing, EOF, and Bidirectional Half-Close

The second example demonstrates: a 4-byte length header; a payload written across **two** `write` calls; `readFully` reading the exact byte count regardless of how segments/chunks were transported; and the client half-closing its send direction while **still reading the response** from the server.

Save as **`TcpFrameAndHalfClose.java`**:

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpFrameAndHalfClose {
    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress());
             Socket client = new Socket(
                InetAddress.getLoopbackAddress(), listener.getLocalPort());
             Socket server = listener.accept()) {

            client.setSoTimeout(10_000);
            server.setSoTimeout(10_000);

            byte[] payload = "Tiếng Việt TCP".getBytes(StandardCharsets.UTF_8);
            DataOutputStream sender = new DataOutputStream(
                    client.getOutputStream());

            sender.writeInt(payload.length);
            sender.write(payload, 0, 2);
            sender.write(payload, 2, payload.length - 2);
            sender.flush();
            client.shutdownOutput();

            DataInputStream receiver = new DataInputStream(
                    server.getInputStream());

            int length = receiver.readInt();
            if (length < 0 || length > 1024) {
                throw new IOException("Invalid frame length: " + length);
            }

            byte[] frame = new byte[length];
            receiver.readFully(frame);
            System.out.println("Frame: " +
                    new String(frame, StandardCharsets.UTF_8));
            System.out.println("Client EOF: " + (receiver.read() == -1));

            server.getOutputStream().write(new byte[] {'O', 'K'});
            server.shutdownOutput();

            byte[] reply = new byte[2];
            new DataInputStream(client.getInputStream()).readFully(reply);
            System.out.println("Reply: " +
                    new String(reply, StandardCharsets.UTF_8));
        }
    }
}
```

Run:

```sh
javac -encoding UTF-8 TcpFrameAndHalfClose.java
java TcpFrameAndHalfClose
```

Deterministic stdout on a successful run:

```text
Frame: Tiếng Việt TCP
Client EOF: true
Reply: OK
```

Sequence:

1. The client sends `writeInt(payload.length)` and the UTF-8 payload; two payload `write` calls do not create two messages.
2. The client calls `shutdownOutput()`. The server reads the complete frame via `readInt` + `readFully`; the `read()` call after the frame returns `-1` once all data before FIN has been received.
3. The server still writes `OK` back in the reverse direction, then calls `shutdownOutput()`. The client can still read the two-byte response because TCP is full-duplex.

`setSoTimeout(10_000)` sets a wait limit for **a blocking read call on the socket**; it can throw `SocketTimeoutException` if no data arrives in time, but it is not an absolute timer for an entire long message trickled in slowly. A production system also needs total time limits, byte limits, connection limits, and appropriate cancellation/closing behavior.

In the example, the response is fixed at exactly two bytes so the client uses `readFully(reply)`. For real responses, you must also define framing, length limits, and error states. `shutdownOutput` is a half-close mechanism, **not an application ACK**, and does not certify that data was committed.

## 8. EOF, FIN, RST, and When Is a Connection Considered Finished?

- **FIN / orderly shutdown:** when the peer cleanly closes its send direction and all bytes prior to FIN have been read, the stream returns EOF (`-1`). In the opposite direction, the connection may still continue sending data.
- **`Socket.shutdownOutput()`:** signals that the application will send no more bytes in this direction; any bytes queued before the end signal remain before FIN in stream order. Subsequent writes after shutting down output are no longer valid.
- **`Socket.close()`:** releases the socket and both streams on the Java side. Behavior at the TCP layer depends on connection state/buffers/options; **do not infer that all pending bytes have been processed by the remote application**.
- **RST / abort:** the connection may be reset and the reading/writing side encounters `SocketException`/`IOException` instead of a clean EOF. Similarly, an application crash, killed process, or network drop can leave a message only partially sent or received.
- **`Socket.isConnected()`:** only indicates whether the socket was ever successfully connected; it is not a current health check. `isClosed()` refers to the local object's closed state, not proof that "the peer just finished reading."
- **Half-open or unreachable connections:** timeouts, keepalive, or application-layer heartbeats may be needed for detection. TCP keepalive is not an accurate business timer and typically does not respond quickly by default.

When reading a frame, if only the header or a few payload bytes arrive before EOF, the protocol must treat that frame as **incomplete**. Do not pass a partial payload into business logic as a valid message.

## 9. Handling Errors and Latency in Blocking Java Sockets

| Issue | What the application should do |
| --- | --- |
| Connection takes too long | Use `Socket.connect(endpoint, timeoutMillis)` for connect timeout and handle `IOException` |
| `read` can block indefinitely | Use `setSoTimeout` for blocking reads; add an end-to-end deadline at the protocol layer if needed |
| Untrusted length header | Check `0 <= length <= MAX_FRAME_BYTES` (if empty body is allowed), never allocate unboundedly |
| `EOFException` mid-frame | Discard the incomplete frame, close the session with error handling, and log the failure point clearly |
| Write fails due to peer/network error | Catch `IOException`; do not assume "not yet processed on the server" |
| Many peers send faster than processing capacity | Limit connections/buffers/queues, apply backpressure, avoid unbounded threads or arrays |
| Reconnecting after failure | Use a new TCP session; explicitly design replay/resume, message IDs, and duplicate handling if business logic requires it |

A `SocketTimeoutException` during a read indicates that **the read call timed out waiting for data**; it does not mean the server definitely has not executed the request. Similarly, a successful write is no guarantee that the peer has read it. If the application retries immediately without idempotency, an operation such as debiting funds or creating an order may execute twice.

Do not use `Thread.sleep` as a mechanism to "wait for the full message": network data has nondeterministic latency, and sleeping cannot determine content boundaries. Use framing and APIs that read the required byte count.

## 10. To Know the Server Executed Business Logic, You Need an Application ACK

Protocol example for a non-repeatable operation:

```text
Client                               Server
  | -- COMMAND{id=123, body=...} -->  |
  |                                   | check idempotency key
  |                                   | execute and durably commit
  | <-- RESULT{id=123, committed} --  |
```

**Design rules:**

1. Assign a stable **request ID/idempotency key** for the same business intent. Retries reuse the old key rather than generating a new intent.
2. The server checks the key, stores the result, and applies changes using an appropriate consistency mechanism (e.g., a transaction with a unique constraint) so concurrent retries do not produce multiple effects.
3. Send the **application response/ACK only after the commit point** defined by the protocol; clearly specify whether a response means "request received," "queued," or "committed."
4. When the connection drops after commit but before the client receives the response, the client can retry with the same key; the server returns the stored result or already-processed status.
5. Define the scope and retention period of keys, handle key reuse with a different payload, and avoid purging deduplication history too early.

Thus, **TCP preserves byte ordering within a connection**, while retry safety and duplicate prevention are **an application-layer contract coordinated with storage**. No flag on `Socket` automatically turns TCP writes/ACKs into an exactly-once transaction.

## 11. Performance: Buffering, Backpressure, and Head-of-Line Blocking

TCP optimizes for transferring **bytes**, not preserving the number of `write` calls. Very small writes can be affected by Nagle's algorithm, delayed ACKs, kernel buffering, and network scheduling; very large writes may be segmented. `Socket.setTcpNoDelay(true)` adjusts Nagle behavior to improve latency in some small-write patterns; it **does not** turn TCP into a message protocol and may increase segment count/overhead.

When a peer reads slowly, the receive window shrinks and the sender may stall; when the network is congested, congestion control reduces throughput. When an earlier byte has not arrived, TCP must fill the ordering gap before delivering later bytes; a "small, urgent" business command sent on the same stream does not automatically overtake preceding data.

Therefore, on the Java processing path:

- Define **framing** and **maximum bytes per message**, avoiding reading an open stream indefinitely with unbounded `readAllBytes()`.
- Measure **p95/p99 latency**, connection count, queued bytes, timeouts, retry counts, and buffer pressure; do not use `write`/`read` counts as a proxy for message counts.
- If using `BufferedOutputStream`, flush at the **point a complete frame** needs to be emitted per the protocol; do not expect flush to act as a TCP ACK.
- Set total time and throughput limits; stop accepting or executing when downstream processing is overloaded instead of building unbounded queues.
- With multiple request types on one connection, consider processing order and higher-layer multiplexing protocols; do not assume TCP automatically bypasses a stalled stream.

## 12. Common Mistakes and How to Fix Them

**Mistake 1: "One `write` corresponds to one `read`."** If you call `read(buffer)` once and parse JSON assuming a full request, you may get half a JSON document or multiple JSON documents concatenated together. **Fix:** length-prefix, a delimiter with escaping/limits, or a protocol with explicit boundaries.

**Mistake 2: "`read` didn't fill the buffer, so the peer sent too little."** Returning fewer bytes than the buffer size is valid and does not prove data loss. **Fix:** loop until the exact byte count required by framing is read; handle EOF/timeouts.

**Mistake 3: "`available() == 0` means the message is over."** 0 may simply mean no bytes are immediately readable at that instant. **Fix:** use a framing protocol, not timing heuristics about data availability.

**Mistake 4: "`flush` is a message terminator."** Flush only affects buffering layers and inserts no delimiter. **Fix:** write a real header/delimiter and flush if a buffering wrapper is used.

**Mistake 5: "TCP ACK means the server saved the transaction."** TCP ACKs belong to the transport layer. **Fix:** post-commit application responses and idempotency on retries.

**Mistake 6: "Already sent last time, so reconnecting will resume automatically."** A new TCP connection has a new byte stream and state; unacknowledged bytes or prior business processing state are not synchronized by TCP across two sessions. **Fix:** design explicit resume/replay and deduplication.

**Mistake 7: "TCP absolutely guarantees data always arrives."** Networks, hosts, processes, the TCP stack, and timeouts can fail; the application may only know an *indeterminate* outcome. **Fix:** handle EOF, resets, timeouts, errors, and clearly define confirmation/retry behavior.

**Mistake 8: "TCP protects content from being read or modified."** TCP checksums do not encrypt data or authenticate the sender. **Fix:** use appropriate TLS along with application-layer identity verification/authorization.

## 13. Self-Check Questions

1. A client calls `write("A")` then `write("B")`; the server calls `read(buffer)` once and receives bytes `AB`. Is this an error? **No:** TCP preserves ordering, not write boundaries.
2. The server receives a length-prefix via `readInt()`, then a single `read(payload)` returns fewer bytes than declared. Is data lost? **Inconclusive:** use `readFully`/a loop and handle EOF or timeouts.
3. A client writes successfully and then loses the connection before the response; is it safe to resend the "deduct 100" command? **Not yet:** the old command may have already committed. You need an idempotency key and a queryable/retrievable business result.
4. When the server calls `shutdownOutput`, can the client still send data to the server? **Yes**, because the server only closed its **send** direction; the server's receive side can still operate until closed.
5. Since TCP has a checksum, can we skip TLS? **No:** checksums provide no confidentiality, authentication, or cryptographic integrity.

## 14. Practical Takeaways

Keep two separate propositions in mind:

- **TCP:** bytes are delivered to the receiving application **in exact order within each direction of a connection**, with retransmission, receive windows, and congestion control; when the network path or an endpoint fails, the connection may stop before transmission completes.
- **Application:** must define **message boundaries**, validate lengths/formats, manage timeouts, handle business responses, and implement retries/idempotency. `write()`, FIN, or TCP ACKs do not replace a post-commit response.

Standard API references: [Java SE 17 Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html), [ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html), [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html), [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html), and [RFC 9293 — Transmission Control Protocol](https://www.rfc-editor.org/rfc/rfc9293).