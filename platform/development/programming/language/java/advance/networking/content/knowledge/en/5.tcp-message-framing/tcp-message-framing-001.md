# Why Does One write Not Correspond to One read?

## 1. The Core Problem: TCP Transmits a Byte Stream, Not "Function Calls"

Imagine a Java client writing a message:

~~~java
byte[] data = "HELLO".getBytes(StandardCharsets.UTF_8);
socket.getOutputStream().write(data); // A single write(...) call
~~~

The server side might receive it with **one read() of all 5 bytes**, or it might need **multiple read() calls** to receive all of them. Conversely, two consecutive `write(...)` calls on the client could be retrieved by the server in **one read()** if the buffer and read timing allow.

This is **normal, standard-compliant TCP behavior**, not TCP losing or duplicating messages.

**Principle to remember: TCP is an ordered byte stream. TCP does not store or transmit boundaries between the application's write() calls.**

~~~text
Java Client                                      Java Server

write("ABC") --\
                \                              /--> read(...) = "AB"
write("DEF") ---->  BYTE STREAM: A B C D E F  --<
                                               \--> read(...) = "CDEF"

Another valid split:

write("ABC") --\
                \                              /--> read(...) = "ABCDEF"
write("DEF") ---->  BYTE STREAM: A B C D E F  --<
~~~

The two diagrams illustrate **possible outcomes**, not a schedule you can force TCP to reproduce by sleeping for a few milliseconds. If the application needs to receive the messages "ABC" and "DEF" separately, **the application protocol itself must mark message boundaries**.

A more accurate statement is:

> One write() represents an operation to send bytes on the application side. One read() represents an operation to retrieve some available bytes (or wait for bytes) on the receiving side. There is no one-to-one guarantee between those two operations.

## 2. Separating Three Commonly Confused Types of Boundaries

There are at least three different types of boundaries:

| Boundary | Who defines it? | Is it preserved on the receiving side? |
| --- | --- | --- |
| **Application's write(...) call** | Sender code | **No**: TCP does not turn it into a "record" |
| **TCP segment / IP packet** | TCP/IP stack, network, and devices | **No**: read() is not an API for reading individual segments |
| **Application message** | Protocol defined by the application or a standard like HTTP | **Only** if the application has a way to frame and decode |

A single message can be split across multiple segments. Multiple pieces of data written close together can be placed by TCP into segments in a way that does not match the number of writes. Once the receiving side has bytes in its receive buffer, a single read can retrieve data originating from multiple previous writes.

Even if Wireshark shows "one TCP segment containing one message" in a few runs, that is **not an API contract**. Other runs may have different segmentation, offloading, buffer sizes, and scheduling timing.

**What does TCP guarantee while the connection is active?**

- Bytes are delivered to the receiving side **in the exact order of the stream**, without reordering application-created boundaries.
- TCP has checksums, acknowledgments, and retransmission mechanisms to maintain integrity and deliver bytes while possible.
- TCP does not inherently know "this is an order," "this is a JSON," or "this is the end of a message."
- When the connection fails, the application still may not know how far the other side has processed the request. A write() returning successfully is **not a business receipt**.

TCP provides a reliable byte-stream foundation within the protocol's capabilities; it **does not provide transactions, exactly-once business processing, or application acknowledgments**.

## 3. Why Can One write() Require Multiple read() Calls?

### 3.1. The Receiver's Buffer Has a Limited Size

For example, the client writes 16 bytes with a single write:

~~~text
Client: write("HELLO_TCP_STREAM")    // 16 UTF-8 bytes

Server: byte[] buffer = new byte[4];

read(buffer) <= 4 bytes per call
~~~

Even if all 16 bytes are already in the receive buffer, the server **cannot** retrieve more than 4 bytes in a single `read(buffer)` with a 4-byte buffer. It must read at least **4 times with positive results** to get all 16 bytes. If the data arrives more fragmented, it may need **more than 4 times**.

This is a reproducible way to demonstrate it without relying on intentionally slowing down the network: **a program-set buffer limit** is enough to cause one write to be consumed by multiple reads.

### 3.2. Bytes May Not Arrive Simultaneously

Even when the server's buffer is large, a read call can execute when only part of the bytes are available. With a blocking socket, **InputStream.read(byte[], off, len)** waits until there is data, EOF, or an error; once data is available, it **is allowed to return fewer than len bytes**. There is no condition to "wait until the sender's entire message is complete" because TCP does not know how long that message is.

For example, the client wants to send 10,000 bytes, and the server reads into a 16 KiB buffer. Any positive result **no greater than 10,000** can be the number of bytes read, depending on when data is available. The server must not conclude that a read < 10,000 means the sender sent an incomplete message.

### 3.3. The Network and Operating System Handle Bytes Independently

Factors that can change the number of bytes per read:

- Fragmenting the stream into TCP segments suited to MSS/MTU and TCP policies.
- Operating system send/receive buffers, congestion control, and flow control.
- Thread scheduling, and the number of bytes available when read is called.
- `BufferedInputStream`, `BufferedReader`, TLS, or a framing layer above having its own buffer.
- How the code chooses buffer sizes or read timing.

**Do not look for a "standard TCP packet size" and use it as a message size.** Segment size and message size serve two different layers.

## 4. Why Can Multiple write() Calls Be Read Together by One read()?

Suppose the sender writes twice:

~~~java
OutputStream out = socket.getOutputStream();
out.write("HELLO".getBytes(StandardCharsets.UTF_8));
out.write("WORLD".getBytes(StandardCharsets.UTF_8));
~~~

The receiver has a 64-byte buffer and executes `read()` after the bytes have arrived; it can receive **HELLOWORLD** in one call. It can also receive **HEL**, then **LOWORLD**, or another split that still preserves the order.

Common points of misunderstanding:

- **flush()** on a `BufferedOutputStream`/`BufferedWriter` pushes buffered data down to the underlying output stream; it **does not create a message boundary in TCP** and does not confirm that the server has processed it.
- **Socket.setTcpNoDelay(true)** affects Nagle's algorithm; it does not turn TCP into a protocol with record boundaries.
- **Thread.sleep(...)** between two writes might make a single test produce a different result, but it does not turn a pause into a reliable delimiter.
- **One TCP segment does not have to correspond to one read() call**. You can read one segment through multiple small reads or read data from multiple segments through one large read.

For the application, the question "how many times did the sender call write?" is not the way to determine the number of messages.

## 5. Exact Contracts of Java Read/Write APIs

### 5.1. InputStream.read

With a blocking socket:

~~~java
byte[] buf = new byte[1024];
int n = socket.getInputStream().read(buf);
~~~

Meaningful results:

| n | Meaning |
| --- | --- |
| **n > 0** | Exactly n bytes were read into the buffer, at most 1024; n is not the message size |
| **n == -1** | Reached **end-of-stream** after all readable bytes are exhausted; usually because the peer closed its send half / closed the connection normally |
| **n == 0** | Not a normal state for a blocking read with a positive-length buffer; specifically can occur when requesting to read **0 bytes** |

A blocking `read(...)` with a positive length usually waits for at least one byte, EOF, or an exception. It **does not automatically read the full** requested length. If a message needs exactly 4096 bytes, you must loop or use an API that reads enough bytes.

**Do not do this:**

~~~java
// Incorrect example: assuming one read is one message.
byte[] buffer = new byte[4096];
int n = in.read(buffer);
String message = new String(buffer, 0, n, StandardCharsets.UTF_8);
process(message);
~~~

The example also ignores **n == -1** and can decode incorrectly when a UTF-8 character is split between two reads. Even when n is positive, the data may only be part of a message or multiple messages stuck together.

### 5.2. readFully and readNBytes

In Java 17, there are useful APIs when **the protocol already knows the number of bytes to read**:

- **DataInputStream.readFully(byte[])**: attempts to read enough bytes to fill the array; if EOF is encountered before enough bytes are read, it throws **EOFException**.
- **InputStream.readNBytes(int len)**: reads at most len bytes, trying to get all of them while data remains; if EOF is encountered early, it may return an array **shorter than len**. Code needs to check the length if exactly len is required.
- **InputStream.readNBytes(byte[], off, len)**: returns the number of bytes actually read, which may be less than len if EOF has been reached.
- **InputStream.readAllBytes()**: reads until **EOF**; do not use it as "finished reading one message" when the connection is kept open to exchange multiple messages.

An API that "reads N bytes" is a step in implementing framing; **it cannot guess N bytes from TCP**. The application must know N from the contract (fixed size, header length, etc.).

### 5.3. OutputStream.write and SocketChannel.write

A call to **OutputStream.write(byte[])** on a blocking socket attempts to push bytes through the output stream and may block/fail during the operation. When `write()` returns, you must not infer that the peer has read, parsed, or processed the message. If the connection fails midway, the application may not know how much the other side received.

With **java.nio.channels.SocketChannel**, the **write(ByteBuffer)** method returns **the number of bytes actually written**. Especially in **non-blocking** mode, it may write **fewer than the remaining bytes**, or even **0**. Therefore, you need to check **buffer.hasRemaining()**, retain the unsent portion, and register for writability using **Selector.OP_WRITE** instead of busy-spinning when no more can be written.

Similarly, **SocketChannel.read(ByteBuffer)** in non-blocking mode can return **0** if no bytes are available at that moment, **-1** on EOF, or a positive number of bytes; this is still a byte stream without message boundaries.

## 6. Runnable Java 17+ Example: One write, Multiple reads

The following program opens two Java processes on loopback TCP port **5051**. The client writes the payload **HELLO_TCP_STREAM** (16 ASCII/UTF-8 bytes) with **a single out.write(payload) call**. The server deliberately reads the payload into a **4-byte** array, so it must call read multiple times. Every message size is sent via a **4-byte length-prefix**, avoiding having to guess when enough has been read.

**Demo protocol:**

~~~text
Request client -> server:
+----------------------------+------------------------+
| length: 4 byte signed int  | payload: length bytes  |
| big-endian (writeInt)      | UTF-8                  |
+----------------------------+------------------------+

Reply server -> client:
+----------------------------+------------------------+
| length: 4 byte signed int  | payload: length bytes  |
+----------------------------+------------------------+
~~~

The length-prefix is part of the **application protocol**; TCP does not add it automatically. The maximum limit of 1024 bytes for a request and 64 bytes for a response is just a **self-imposed limit** in this example.

### File ChunkedReadServer.java

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class ChunkedReadServer {
    public static void main(String[] args) throws IOException {
        try (ServerSocket listener = new ServerSocket(
                5051, 50, InetAddress.getLoopbackAddress())) {
            System.out.println("Server ready");

            try (Socket client = listener.accept()) {
                client.setSoTimeout(5000);

                DataInputStream in =
                        new DataInputStream(client.getInputStream());
                DataOutputStream out =
                        new DataOutputStream(client.getOutputStream());

                int length = in.readInt();
                if (length < 0 || length > 1024) {
                    throw new IOException("Invalid frame length: " + length);
                }

                ByteArrayOutputStream assembled =
                        new ByteArrayOutputStream();
                byte[] part = new byte[4];
                int calls = 0;

                while (assembled.size() < length) {
                    int requested = Math.min(
                            part.length, length - assembled.size());
                    int n = in.read(part, 0, requested);

                    if (n == -1) {
                        throw new EOFException("Truncated frame");
                    }
                    if (n == 0) {
                        continue;
                    }

                    assembled.write(part, 0, n);
                    calls++;
                }

                String message =
                        assembled.toString(StandardCharsets.UTF_8);
                System.out.println("Server received: " + message);
                System.out.println("Multiple reads: " + (calls > 1));

                byte[] reply = "ACK".getBytes(StandardCharsets.UTF_8);
                out.writeInt(reply.length);
                out.write(reply);
                out.flush();
            }
        }
    }
}
~~~

### File SingleWriteClient.java

~~~java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class SingleWriteClient {
    public static void main(String[] args) throws IOException {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 5051), 3000);
            socket.setSoTimeout(5000);

            DataOutputStream out =
                    new DataOutputStream(socket.getOutputStream());
            DataInputStream in =
                    new DataInputStream(socket.getInputStream());

            byte[] payload = "HELLO_TCP_STREAM"
                    .getBytes(StandardCharsets.UTF_8);

            out.writeInt(payload.length); // 4-byte header
            out.write(payload);            // Exactly one write for payload
            out.flush();
            System.out.println("Client sent: HELLO_TCP_STREAM");

            int length = in.readInt();
            if (length < 0 || length > 64) {
                throw new IOException("Invalid reply length");
            }
            byte[] response = new byte[length];
            in.readFully(response);        // Read exact length bytes

            System.out.println("Client received: " +
                    new String(response, StandardCharsets.UTF_8));
        }
    }
}
~~~

### Compile and Run

Requires **JDK 17 or later**. Place both files in the same directory and compile:

~~~bash
javac --release 17 -encoding UTF-8 ChunkedReadServer.java SingleWriteClient.java
~~~

First terminal:

~~~bash
java ChunkedReadServer
~~~

Wait for the server to print **Server ready**, then run in the second terminal:

~~~bash
java SingleWriteClient
~~~

**Expected server stdout:**

~~~text
Server ready
Server received: HELLO_TCP_STREAM
Multiple reads: true
~~~

**Expected client stdout:**

~~~text
Client sent: HELLO_TCP_STREAM
Client received: ACK
~~~

The program logic was verified with the Java runtime: the output matched both stdout groups above.

**Why is the result `Multiple reads: true` deterministic?** The string is exactly **16 UTF-8 bytes**. The server reads at most **4 bytes** per payload read. Even if the network delivers all 16 bytes at once, at least **4 positive read calls** are needed. If the OS delivers the bytes in smaller chunks, more than 4 calls may be needed; the program intentionally prints only a boolean, not an assumed read count.

**Purpose of the client's first two operations:**

~~~java
out.writeInt(payload.length); // 4-byte header length
out.write(payload);            // payload sent in a single write
~~~

The client writes the header and payload as two separate write operations, but **the payload has only a single write call**. The server reads the header using **readInt()**, then reads the payload using **read(...)** calls with a 4-byte buffer. Both sides know the exact payload boundary is **16 bytes as declared by the header**, without relying on the number of writes or reads.

The server accepts only one connection to keep the lesson easy to follow and binds to **loopback** to run on the same machine. If you encounter **BindException**, port 5051 may already be in use: change to the same port number in both programs. If the client runs before the server, `connect` may be refused. **setSoTimeout(5000)** limits the wait time for socket reads; it does not become a deadline for the entire business operation.

## 7. How to Solve the Practical Problem: Message Framing

To transmit **multiple messages** over a single TCP connection, both sides must agree on **how to determine the start/end** of each message. There are four common approaches.

| Approach | Rule | Suitable for | Common pitfalls |
| --- | --- | --- | --- |
| **Fixed-size** | Each message is exactly N bytes | Simple binary records, fixed structure | Must agree on N and layout |
| **Delimiter** | Message ends with a separator character/sequence, e.g. LF | Text commands, line-based protocols | Payloads containing the delimiter must be escaped; need line length limits |
| **Length-prefix** | Header specifies the size of the body | Binary, JSON, multiple messages on the same connection | Must bound length to avoid huge allocations |
| **Standard protocol** | Use framing from HTTP, WebSocket, gRPC, etc. | APIs, distributed applications | Follow the exact framing and version of each standard |

**TCP does not provide framing**, so none of these options appear automatically when creating a socket.

### 7.1. Delimiter Using Text Lines

If the protocol defines each message as **a UTF-8 line ending with LF**, the sender can use `BufferedWriter.write(...)`, `newLine()`, `flush()`; the receiver uses `BufferedReader.readLine()`.

~~~java
// API illustration within an open TCP session.
out.write("PING");
out.newLine();
out.flush();

String command = in.readLine();
~~~

**readLine()** may invoke underlying byte reads multiple times; it returns a logical single-line string, not a TCP packet. If the stream ends before any new character arrives, `readLine()` returns `null`; if EOF arrives after some characters without a delimiter, the API may return the read characters as the last line. Therefore, protocols requiring a **mandatory newline** must check separately for EOF/truncated messages if needed.

Only use this example when the payload **does not contain unescaped LF**. A multi-line JSON cannot by default be received in full by a single `readLine()`.

### 7.2. Length-prefix

Helper class example (illustrative snippet, **not a standalone Java program**, placed inside a class that already imports `java.io.*`):

~~~java
static byte[] readFrame(DataInputStream in) throws IOException {
    int n = in.readInt(); // 4 bytes, big-endian
    if (n < 0 || n > 1_048_576) {
        throw new IOException("Invalid frame length");
    }
    byte[] payload = new byte[n];
    in.readFully(payload);    // Loops internally until n bytes are read or EOFException
    return payload;
}

static void writeFrame(DataOutputStream out, byte[] payload)
        throws IOException {
    if (payload.length > 1_048_576) {
        throw new IOException("Frame too large");
    }
    out.writeInt(payload.length);
    out.write(payload);
    out.flush();
}
~~~

With multiple messages on the same socket, call **readFrame(...) for each message**. The receiving side must read the full header before deciding how long the body is, then read **exactly** that many body bytes. The first byte after the body is the start of the next header. Do not derive `n` from the number of bytes `read()` returns.

The **readFully()** operation may have to read from the socket multiple times, but once it succeeds, the application has a message of the exact size. If EOF arrives early, **EOFException** signals a truncated frame. A **SocketTimeoutException** does not mean "end of message"; it indicates that the read exceeded the timeout.

**Do not decode UTF-8 in the middle of a message if multi-byte characters could be split.** With the fully assembled payload, use **new String(bytes, StandardCharsets.UTF_8)** or a decoder matching your validation policy. If you must stream-decode by chunk, use a stateful **CharsetDecoder** to handle characters spanning multiple chunks.

### 7.3. Ending with EOF

Some simple protocols send all data and then call **shutdownOutput()** or close the sending side, letting the receiving side read until EOF. This makes sense **only when EOF itself is defined as the end of the message**, such as a one-way stream. It is not suitable for marking multiple consecutive messages on a connection that needs to stay open, and easily causes deadlocks if both sides wait for the other to close.

**InputStream.readAllBytes()** and loops reading until `-1` follow this principle: they complete when EOF appears, **not** when the sender finishes a single `write` call.

## 8. Understanding EOF, Timeout, Close, and Flush Correctly

### When does read() return -1?

With TCP socket input, `-1` usually appears after the peer has finished closing its sending direction and the remaining bytes have been consumed. This indicates **the stream has ended**, not that **any particular application message** is complete.

For example, the server receives a request whose header specifies 100 bytes, but reads only 70 bytes before EOF: the message is **incomplete** and must be reported as an error; those 70 bytes must not be processed as a valid request.

### What if the peer does not close?

A server reading "until -1" can **wait forever** when the client intentionally keeps the socket open to wait for a response. Both sides waiting for each other will cause an application-layer deadlock. Use **delimiters, length-prefix, or a standard protocol** instead of relying on connection termination.

### Is a timeout a delimiter?

**No.** `Socket.setSoTimeout(n)` sets a blocking time limit for each read operation; when the time expires, it may throw `SocketTimeoutException`. Slowly arriving data can still belong to the same valid message; and a malicious peer can send small pieces so that each read does not time out. The application needs to add a **total time limit for the entire frame** when appropriate.

### Does flush() mean the other end has finished reading?

**No.** With a writer/buffered stream, `flush` pushes data from that layer's buffer down to the next stream. It does not wait until the receiving side performs a `read`, nor does it prove the application has decoded or committed a transaction. To know a request was processed, build **application-layer acknowledgments** and deduplication rules.

### Can close() replace framing?

Not in cases requiring multiple requests/responses on the same connection. Close/shutdown only serves the stream lifecycle. If a protocol design uses EOF as a delimiter, it must specify this explicitly; that approach cannot reuse the same sending direction for subsequent messages.

## 9. Common Coding Mistakes

### Mistake A: reading once and parsing immediately

~~~java
int count = input.read(buffer);
parseRequest(buffer, count); // Wrong if a complete frame has not been determined
~~~

You may have received only part of a request or multiple requests merged together. Fix: a framing decoder handles **header/body/delimiter** and keeps leftover bytes to parse the next message.

### Mistake B: using buffer.length as the number of bytes read

~~~java
byte[] buffer = new byte[1024];
int count = input.read(buffer);
System.out.println(new String(buffer, StandardCharsets.UTF_8));
~~~

This snippet can print stale bytes or NUL characters because **buffer.length = capacity**, not the number of newly received bytes. If the actual goal is to display the chunk read, use the range **[0, count)** after checking `count > 0`. However, displaying chunks still does not solve framing.

### Mistake C: using available() to calculate message length

~~~java
int size = input.available(); // Not the total message length!
~~~

**available()** is an estimate of bytes that can be read immediately without blocking in the stream's context; it does not promise that the sender has finished sending or that bytes in flight on the network have arrived. `size == 0` does not confirm the message has ended.

### Mistake D: sleep or TCP_NODELAY to force read to match write

Artificial delays and socket options only affect timing/packing; they do not create boundaries. The right lesson is to **design the protocol**, not try to "synchronize" read/write calls by luck.

### Mistake E: receiving UTF-8 strings in arbitrary chunks

A Vietnamese character can span two reads. If each chunk is decoded separately with `new String(chunk, UTF_8)`, the decoder may produce replacement characters, corrupting the text. The fix is to assemble the complete frame bytes before decoding or use a stateful streaming decoder.

### Mistake F: trusting length from the network

If a peer sends a header requesting an allocation of gigabytes, creating an array directly from that value can exhaust memory. Always **limit size, frame count, timeouts, rate, and total data** before allocating. If reading fails to complete, discard the frame/connection according to the contract.

### Mistake G: parsing a frame and discarding leftover bytes

A single read can contain the end of frame A and the start of frame B. If writing a buffer-based parser yourself, you must **keep unconsumed bytes** to parse frame B. Using `DataInputStream.readFully` with a length-prefix helps reduce the risk of reading past a frame's boundary.

### Mistake H: treating a successful write as "order created"

If the connection drops after `write` but before the response, the client may not know whether the server processed it. Use a **request ID/idempotency key**, acknowledgments, and reconciliation mechanisms suited to the business logic. TCP does not guarantee exactly-once processing for business operations.

## 10. A Before–After Example in a Real Application

Suppose the client needs to send two task-creation requests over **a single TCP connection**:

~~~text
Request A = {"task":"A"}
Request B = {"task":"B"}
~~~

**Wrong way:** execute `write(A)`, `write(B)`; the server reads once for A, then reads once for B. If TCP merges the two payloads or splits mid-JSON, parsing fails or blocks. The fact that both requests are JSON **does not solve boundaries**: closing braces are not enough for a simple parser if there are escaped strings, nested JSON, or trailing data.

**Right way:** choose a framing scheme, for example 4-byte length-prefix + UTF-8 JSON for each request:

~~~text
[4-byte length][12-byte JSON A][4-byte length][12-byte JSON B]
   complete frame A               complete frame B
~~~

The header is **4 big-endian bytes** written by `DataOutputStream.writeInt(...)`, while each ASCII JSON payload in the example is **12 UTF-8 bytes**. In a real system, calculate the length with `payload.getBytes(StandardCharsets.UTF_8).length`; do not use `String.length()` or hard-code the length.

The server reads header A, reads the full body A, and parses; then reads header B, reads the full body B, and parses. TCP can deliver the two frames across any number of reads, but **the boundaries are restored by the length-prefix**. If the client/server uses HTTP or WebSocket, use the standard protocol's framing instead of a custom protocol.

## 11. Further Distinctions with UDP, NIO, and TLS

**UDP:** `DatagramSocket.receive(...)` receives by **datagram**, not byte stream. UDP preserves datagram boundaries if the datagram arrives, but does not guarantee delivery, order, or non-duplication. If the receive array is too short, the excess may be truncated per the API. Do not take UDP properties and infer them back onto TCP.

**Java NIO:** `SocketChannel` in non-blocking mode can read 0 or write 0; the application must manage `ByteBuffer.position`/`limit` and an incremental parser. The parser might receive part of a header on the first read, part of the body on the next, or multiple frames at once. In practice, you need a state machine such as **READ_HEADER → READ_BODY → EMIT_FRAME → READ_HEADER** and retain unconsumed bytes.

**TLS:** `SSLSocket` or the TLS layer adds encryption/buffering/records underneath, but the application's `InputStream` still does not automatically turn each `write` into a business-layer message. TLS record boundaries are not the message definition of the API you design. Choose appropriate framing at the application layer.

## 12. Knowledge Check Questions

**Question 1.** Client calls `write()` for 100 bytes once; the server has a 1024-byte buffer. Is the server guaranteed to read all 100 bytes in the first `read`?  
**Answer:** No. It may read fewer than 100 bytes; `read` depends on available bytes and stream state. You must know the message size and read enough bytes.

**Question 2.** Client calls `write()` twice, 50 bytes each; can the server receive 100 bytes in a single `read`?  
**Answer:** Yes, if 100 bytes are already available and the buffer is large enough. Two writes do not necessarily correspond to two reads.

**Question 3.** Why is the example server guaranteed to print `Multiple reads: true`?  
**Answer:** The payload is 16 bytes long, but each payload read reads at most 4 bytes. Therefore, at least 4 positive reads are required. This is due to the application buffer size, not by guessing how TCP splits segments.

**Question 4.** Does `read(...)` returning `-1` mean the end of a JSON?  
**Answer:** `-1` means EOF of the stream after remaining bytes. Only treat it as the end of a message if the protocol **deliberately uses EOF as the delimiter** and verifies the message is complete.

**Question 5.** Does setting `TCP_NODELAY` turn each `write` into a message?  
**Answer:** No. `TCP_NODELAY` does not change byte-stream semantics.

**Question 6.** If the length-prefix says 400 bytes but the server receives 250 bytes and then EOF, can the 250 bytes be parsed?  
**Answer:** No. This is an incomplete frame; report `EOFException`/protocol error, do not process as a complete message.

**Question 7.** Why should you not use `String.length()` as the length-prefix of a UTF-8 text?  
**Answer:** Length-prefix represents the **number of bytes**; Unicode characters can take multiple bytes in UTF-8. Use **getBytes(UTF_8).length**.

**Question 8.** When can `InputStream.readAllBytes()` be the right choice?  
**Answer:** When the transmission contract clearly specifies that **the entire stream ends with EOF** and there are appropriate resource limits, such as a one-way data stream of reasonable length. It does not automatically recognize boundaries of multiple messages on a kept-open connection.

## Conclusion

The reason **one write does not correspond to one read** lies in the very contract of the **TCP byte stream**: TCP preserves the order of bytes in the stream, but does not preserve the boundaries created by `write(...)` calls. A `read(...)` only retrieves an amount of bytes suited to the buffer and receive state, so it can read part of one write or data coming from multiple writes.

For a program to work correctly, **design framing** (fixed-size, delimiter, length-prefix, or a standard protocol), **read enough bytes**, **limit resources**, **handle EOF/timeouts**, and only **decode/process when a message is complete**. This is the foundation for building correct TCP servers/clients, whether using Java blocking I/O, NIO, or TLS.

### References

- [RFC 9293 — Transmission Control Protocol, Segmentation section](https://www.rfc-editor.org/rfc/rfc9293.html#section-3.7): TCP does not guarantee a one-to-one relationship between segments, read/write buffers, and application messages.
- [Java 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): `read()`, `readNBytes()`, and EOF conditions.
- [Java 17 — DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readInt()` and `readFully()`.
- [Java 17 — OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): `write()` and `flush()`.
- [Java 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): TCP sockets and read timeouts.
- [Java 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): `read`/`write` with `ByteBuffer` and non-blocking I/O.
