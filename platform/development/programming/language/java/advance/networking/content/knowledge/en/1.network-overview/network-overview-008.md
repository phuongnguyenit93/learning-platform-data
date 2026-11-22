# Foundational Knowledge for Java Network Programming: Byte Streams, Buffers, Charsets, Exceptions, and Concurrency

## 1. Objectives and Big Picture

Network programming is not just calling `Socket` and sending a `String`. A program must work with **bytes**, define message boundaries itself, manage buffers, agree on character encoding, respond properly when connections are slow/dropped, and coordinate multiple tasks concurrently. These five knowledge areas are tightly interconnected:

1. **Byte streams** determine how data flows in and out.
2. **Buffers** affect the number of I/O calls, how data is batched, and how partial packets are handled.
3. **Charsets** define how text is converted to bytes and vice versa.
4. **Exceptions and timeouts** help distinguish normal termination, corrupted data, network errors, and overly slow connections.
5. **Concurrency** allows serving multiple connections, but requires managing resources, ordering, and load.

After this lesson, you should be able to explain why a single `read()` does not correspond to a single message; choose a data framing approach; write a UTF-8 text protocol or binary frame; and properly handle EOF, timeouts, resource closing, and multiple concurrent connections.

### 1.1. Distinguishing TCP, UDP, and Read/Write APIs

- **TCP** provides an **ordered and reliable byte stream while the connection is active**. TCP does not preserve the boundaries of `write()` calls: a single write may arrive across multiple reads; multiple writes may be read together. TCP also does not guarantee that the application layer has processed a message, nor can it recover unacknowledged data after one end loses connection.
- **UDP** transports discrete datagrams; each receive retrieves the data of one datagram, but datagrams may be lost, duplicated, arrive out of order, or be truncated if the receive buffer is too small. Java uses `DatagramSocket`/`DatagramPacket` for the traditional API; the underlying TCP framing rules do not automatically apply to UDP.
- **Java I/O** distinguishes `InputStream`/`OutputStream` (bytes), `Reader`/`Writer` (characters), and NIO APIs such as `ByteBuffer`/`SocketChannel` (byte buffers, configurable as non-blocking). Choosing an API does not replace protocol design.

For example: the sender calls `write("A")` and then `write("BC")`. The TCP receiver might read `"ABC"` in one call, `"A"` + `"BC"`, or `"AB"` + `"C"`. All three are valid. Therefore, the **application protocol** must explicitly specify where a message ends.

## 2. Byte Streams: Reading, Writing, EOF, and Connection Lifecycle

### 2.1. Contracts to Know by Heart

| Operation | Actual Meaning | Must Not Assume |
| --- | --- | --- |
| `in.read()` | One byte (0–255), or `-1` at end of stream | `-1` is not a data byte |
| `in.read(buf, off, len)` | Returns actual number of bytes received; may be less than `len`; `-1` signals EOF | Must not assume all `len` bytes are read |
| `out.write(bytes)` | Sends bytes to the output stream; may block or throw `IOException` | Call completion does not mean the peer has processed it |
| `out.flush()` | Pushes data held in Java's buffer layer down to the underlying stream | Does not guarantee the peer has received/durably written it |
| `close()` | Closes the resource, usually making the socket connection unusable | Does not replace application-layer response exchange |

With `InputStream`, `read(byte[])` usually blocks when no bytes/EOF/error are available yet. A positive result only states that **that many bytes** are ready; the rest of the message may arrive later. Do not use `available()` to measure total message length: it only estimates the number of bytes that can be read immediately without blocking, and `0` does not mean EOF.

If you need **exactly N bytes**, loop until enough are read, or use `DataInputStream.readFully(byte[])`. `InputStream.readNBytes(n)` is available since Java 9, but it can return fewer than `n` bytes on EOF: the caller must still check the length. Avoid `readAllBytes()` on long-lived connections or unbounded payloads because it may wait for EOF and consume excessive memory.

### 2.2. Read Loops and Resource Closing

The following snippet illustrates processing chunks of bytes when the protocol allows reading until EOF; the `consume` method is your own application-level processing:

~~~java
byte[] buffer = new byte[4096];
int count;
while ((count = input.read(buffer)) != -1) {
    consume(buffer, 0, count); // Only use the count bytes just read
}
~~~

This is **not** the pattern for receiving a typical TCP message: on a connection kept open to exchange multiple messages, waiting for EOF can cause both sides to wait for each other indefinitely. Only use read-until-EOF when the protocol genuinely uses EOF as the boundary.

For sockets, you should close them using `try-with-resources`. Closing a `Socket` also closes its streams. If you only need to signal "I am done sending" while still wanting to receive a response, use `socket.shutdownOutput()` according to the **protocol convention**; closing an `OutputStream` obtained from a socket usually closes the entire socket and does not replace a half-close. `shutdownOutput()` signals EOF for the send direction after the written bytes have been sent, while the receive direction can still operate. Do not use half-close as an end marker if your protocol uses length-prefixed frames and reuses connections.

In a network program, always ask: "What indicates that a message is complete?" A valid answer can be a newline, a length, a self-delimiting structure, or EOF per an explicit contract; **never** the number of `read()` calls.

## 3. Buffers: Performance vs. Message Boundaries

### 3.1. `BufferedInputStream` and `BufferedOutputStream`

Buffering batches many small operations into fewer calls to the underlying layer. For example, `BufferedOutputStream` may hold bytes in RAM until full or until `flush()` is called. When implementing a protocol that requires an immediate response, call `flush()` after completing a **frame**, otherwise both sides may deadlock waiting: the server waits for the client's bytes while the client waits for the server's response as the request still sits in the buffer.

Conversely, calling `flush()` after **every byte** defeats the purpose of buffering. Choose flush boundaries based on messages and latency requirements. `BufferedInputStream` may pre-read more bytes than the application logic just consumed; do not open another `Reader` to read competitively from the same socket without a coordination design.

Application-level buffers, OS buffers, and TCP buffers are different layers. They do **not** create message boundaries, nor do they replace payload length validation.

### 3.2. NIO `ByteBuffer`

`ByteBuffer` has three markers to understand:

- `capacity`: fixed capacity.
- `position`: next operation index.
- `limit`: current boundary allowed for reading/writing.

The common cycle when reading bytes from a channel into a buffer is **write into buffer → `flip()` → read available bytes → `compact()` → receive more bytes**. `flip()` sets `limit` to the current write position and resets `position` to 0. `compact()` shifts **unprocessed** bytes to the beginning so frame assembly can continue. `clear()` only resets the indices and treats old data as overwritable; it does not physically erase data and **does not preserve** an incomplete frame.

State example:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.put(new byte[] {10, 20, 30}); // position = 3
buffer.flip();                        // position = 0, limit = 3
int first = Byte.toUnsignedInt(buffer.get()); // 10
buffer.compact();                     // Keeps 20, 30; position = 2
~~~

With `SocketChannel` in non-blocking mode, `read()` can return `0` when no data is currently available; `write()` can also write fewer bytes than remaining. Therefore, you must check `hasRemaining()`, maintain frame state across multiple operations, and use a `Selector`/event loop when choosing this model. Do not carry over the "one write finishes everything" assumption from blocking code into NIO.

## 4. Charset: Character Sequences Are Not Byte Sequences

### 4.1. Consistent Protocol Encoding

Java's `String` represents text as UTF-16 code units, whereas data on the wire is bytes. Use an explicitly specified charset, typically `StandardCharsets.UTF_8`:

~~~java
byte[] wire = "Việt".getBytes(StandardCharsets.UTF_8);
System.out.println("Việt".length()); // 4 UTF-16 units
System.out.println(wire.length);     // 6 UTF-8 bytes
String restored = new String(wire, StandardCharsets.UTF_8);
~~~

`String.length()`, the number of code points, and the number of UTF-8 bytes can differ. For emojis, a single displayed character can take **two** UTF-16 units. Therefore, a binary protocol's "payload length" header must count **bytes after encoding**, not `message.length()`.

Do not use `new String(bytes)` or zero-argument `getBytes()` in a protocol that must behave identically across environments: they depend on the runtime's default charset. For text protocols, both sides must agree on the charset, line separator, and how to handle malformed bytes.

### 4.2. Chunk Boundaries Can Split Multi-Byte Characters

A UTF-8 character can span multiple `read()` calls. If you receive each chunk and immediately call `new String(chunk, UTF_8)`, you may decode a character when only half of its bytes have arrived and produce replacement characters (�). The right approach is to **assemble a complete frame at the byte level before decoding**, or use `InputStreamReader`/`CharsetDecoder` which maintains state across chunks.

- For line-based protocols: `BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))` handles decoding across multiple reads, while `readLine()` determines boundaries based on newlines and strips the line ending from the result. Do not mix `BufferedReader` with `DataInputStream` reading directly from the same socket: the `Reader` may read ahead into bytes belonging to the next frame.
- For length-prefixed frames: read **the exact number of payload bytes**, then decode once. To reject malformed UTF-8, use `StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)`. The default decoder in some convenience APIs replaces errors with a replacement character; choose an explicit policy instead of silently ignoring corrupted data.
- For line-based protocols, explicitly specify `\n` or `\r\n`, the maximum line length, and whether text is allowed to contain newlines. Do not use newline as a delimiter if payloads can contain arbitrary newlines without escaping.

**Note:** `DataOutputStream.writeUTF()` uses Java's "modified UTF-8" and its own length prefix; it is not equivalent to an arbitrary standard UTF-8 frame. Only use it when both sides explicitly agree on that exact format.

## 5. Message Framing: The Rule That Connects the Fundamentals

Because TCP only provides a byte stream, both ends must agree on **framing** before exchanging data. Three common approaches:

| Framing Approach | When Appropriate | What Must Be Controlled |
| --- | --- | --- |
| Delimiter such as `\n` | Simple text commands/lines | Escaping newlines inside data, line length limit, charset |
| Length prefix + payload | Binary frames or arbitrary text | Endianness, prefix size, byte length, maximum limit, mid-frame EOF |
| Connection close/half-close after payload | One-shot send-and-finish protocol | Unsuitable for reused connections/back-and-forth exchanges without agreement |

A common frame format is **[4-byte unsigned/signed length per contract] + [N bytes of UTF-8]**. The example below uses a **32-bit signed integer, big-endian** via `DataOutputStream.writeInt()` and accepts `0 ≤ N ≤ 65_536`. How the length and limits are interpreted must be documented so clients in other languages can interoperate.

The proper receive flow is: **read all 4 length bytes → validate length before allocating → read exact N bytes → decode UTF-8 → process message**. If `readFully` cannot read enough bytes due to EOF, the frame was truncated mid-way and is a protocol error—never silently treat it as a complete message. Frame limits prevent arbitrary memory allocation from a peer-supplied length.

## 6. Exceptions, Timeouts, and Resource Cleanup

### 6.1. Do Not Treat Every Termination as the Same Error

| Symptom | Common Java Signal | Appropriate Handling |
| --- | --- | --- |
| Peer closes normally at protocol boundary | `read() == -1` before a new frame; sometimes `EOFException` when reading prefix | Close session; distinguish valid EOF from an incomplete frame |
| Peer closes mid-length/payload | `EOFException`, `IOException` | Report incomplete frame, discard partial data |
| No bytes within read timeout | `SocketTimeoutException` | Apply deadline/timeout policy; do not treat as EOF |
| Cannot connect or DNS failure | `ConnectException`, `UnknownHostException` | Report exact cause, consider bounded retry |
| Connection reset/dropped during write or read | `SocketException` or `IOException` | Close connection, determine whether operation can be safely retried |
| Invalid UTF-8 payload with strict decoder | `CharacterCodingException` (an `IOException`) | Reject frame per protocol, log safe details |
| Waiting future/task interrupted | `InterruptedException` | Restore interrupt flag and exit per cancellation policy |

**Connect timeout and read timeout are different.** `Socket.connect(address, timeoutMillis)` limits the connection establishment time; `socket.setSoTimeout(timeoutMillis)` sets the timeout for blocking reads on the socket (and `ServerSocket.setSoTimeout` for `accept()`). It is **not** an end-to-end deadline and does not automatically bound all write operations. When a total maximum duration is required, design a separate deadline and socket cancellation/closing mechanism.

A successful `flush()` does not confirm the peer has processed the data. When a client sends a request and hits a timeout before receiving a response, it cannot assume the server did not execute the request. Retrying can cause duplicate side effects. If the operation has side effects, you need a request ID, idempotency, or an application-layer acknowledgment mechanism.

### 6.2. Cleanup and Error Observability

- Open resources close to where they are used, and close them with `try-with-resources` even when exceptions are thrown. Do not swallow `IOException` and continue using a socket in an unknown state.
- Preserve the root cause and context (address, operation, frame/byte count, timeout), but do not log entire payloads containing sensitive data.
- Validate size and checksum/format when required by the protocol; bound input data before allocating and before passing to expensive processing steps.
- When catching `InterruptedException` in a cancellable task: call `Thread.currentThread().interrupt()`, then exit/close resources per contract. Do not assume `interrupt()` always cancels every blocking socket I/O call across all APIs and platforms; closing the socket or using timeouts is the practical control mechanism.

## 7. Concurrency: Multiple Connections, One Clear Protocol

A blocking server typically has an acceptor thread calling `accept()` and handing accepted sockets to workers. The main options are:

- **Thread per connection**: easy to understand, but platform threads, stacks, and context switching have overhead; many slow clients can exhaust resources.
- **Fixed `ExecutorService`** (Java 17+): caps the number of concurrently active workers, but `Executors.newFixedThreadPool` uses an unbounded queue by default; you still need policies for connection limits, timeouts, queue/backpressure, and load shedding.
- **Non-blocking NIO + `Selector`**: fewer threads manage many sockets via per-socket read/write state, at the cost of more complex frame state machines and partial-write handling.
- **Virtual threads** (Java 21+): `Executors.newVirtualThreadPerTaskExecutor()` makes the blocking model easy to scale in terms of thread cost, but it does **not** exempt you from connection, memory, CPU, database, or downstream service limits. This is a Java 21+ option, not a Java 17 API.

**Ownership rule:** each connection should have a clearly coordinated reader thread; if multiple tasks write to the same socket, complete frames must be serialized in order. Using a `DataOutputStream` from multiple threads without proper locking/queuing can interleave message headers/payloads. Do not share a `ByteBuffer` with mutable position across workers without synchronization.

The `accept()` thread should not perform long-running work itself; workers need timeouts and load limits, and must close the socket when a task fails or is rejected. When shutting down the server, stop accepting new clients, close the listener, drain active connections, and await the executor per a graceful shutdown policy. Avoid tight immediate retry loops on persistent I/O errors.

## 8. Runnable Java 17+ Example: Length-Framed TCP Echo

The example runs completely on the machine's **loopback** interface, requiring no external server. The server runs on a worker; the client sends a Vietnamese string; both exchange **[4-byte length, big-endian] + [UTF-8 payload]**. Buffers are flushed after each frame; `readFully()` assembles the full payload across multiple receives; the strict decoder detects corrupted UTF-8. There is a 64 KiB limit and read timeouts to avoid waiting indefinitely.

Save to **FramedEchoDemo.java** (filename must match the public class):

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FramedEchoDemo {
    private static final int MAX_FRAME_BYTES = 64 * 1024;

    private static void send(DataOutputStream out, String message)
            throws IOException {
        byte[] payload = message.getBytes(StandardCharsets.UTF_8);
        if (payload.length > MAX_FRAME_BYTES) {
            throw new IOException("Frame too large");
        }
        out.writeInt(payload.length); // 4 bytes, big-endian
        out.write(payload);
        out.flush();                   // Flush the entire frame through the buffer
    }

    private static String receive(DataInputStream in) throws IOException {
        int length = in.readInt();      // Wait for all 4 length bytes
        if (length < 0 || length > MAX_FRAME_BYTES) {
            throw new IOException("Invalid frame length: " + length);
        }
        byte[] payload = new byte[length];
        in.readFully(payload);         // Wait for all length bytes or EOF
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(payload))
                .toString();
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener =
                     new ServerSocket(0, 1, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(5_000);
            ExecutorService workers = Executors.newSingleThreadExecutor();
            try {
                Future<?> serverTask = workers.submit(() -> {
                    try (Socket peer = listener.accept();
                         DataInputStream in = new DataInputStream(
                                 new BufferedInputStream(peer.getInputStream()));
                         DataOutputStream out = new DataOutputStream(
                                 new BufferedOutputStream(peer.getOutputStream()))) {
                        peer.setSoTimeout(5_000);
                        String request = receive(in);
                        send(out, "ACK: " + request);
                    } catch (IOException error) {
                        throw new UncheckedIOException(error);
                    }
                });

                try (Socket client = new Socket(
                             InetAddress.getLoopbackAddress(),
                             listener.getLocalPort());
                     DataInputStream in = new DataInputStream(
                             new BufferedInputStream(client.getInputStream()));
                     DataOutputStream out = new DataOutputStream(
                             new BufferedOutputStream(client.getOutputStream()))) {
                    client.setSoTimeout(5_000);
                    send(out, "Xin chào mạng");
                    System.out.println(receive(in));
                }

                serverTask.get(); // Propagate the worker's exception if any
            } finally {
                workers.shutdownNow();
            }
        }
    }
}
~~~

Compile/run in the directory containing the file:

~~~bash
javac -encoding UTF-8 FramedEchoDemo.java
java FramedEchoDemo
~~~

Stdout (when the terminal supports Unicode display):

~~~text
ACK: Xin chào mạng
~~~

**Tracing the data flow:**

1. `ServerSocket(0, ..., loopback)` picks an available local port; the server task waits on `accept()`, and the client connects to that exact port.
2. The client encodes `"Xin chào mạng"` as UTF-8; `send()` writes the **byte** length and then writes the payload. Flushing ensures bytes are not held in `BufferedOutputStream`.
3. The server's `readInt()` receives the prefix; validates `length` before allocating; `readFully()` loops at the stream level until all bytes arrive, regardless of how many receives TCP splits the data into.
4. The server performs strict UTF-8 decoding, prepends `"ACK: "`, and sends back a new frame.
5. The client receives the full frame and prints a single line. Socket/stream resources close upon exiting `try-with-resources`. `Future.get()` surfaces any worker exception to `main` instead of letting errors go unnoticed.

This is a **single-connection, single-request/response demo** to demonstrate framing; it is not a production server. A real server needs an `accept` loop for multiple clients, connection and queue limits, authentication if applicable, logging/metrics, a retry policy, and graceful shutdown. For a slow client, the read timeout should be decided by the protocol; the short timeout in the demo is only to avoid unbounded waiting.

### 8.1. Self-Verifying Important Failure Cases

- Change the payload to Vietnamese text with emojis: the UTF-8 byte count can exceed `String.length()`, yet the result remains correct because the prefix comes from `payload.length`.
- Try sending a frame with a negative length or greater than 65,536: `receive()` rejects it **before** allocating the array.
- Send a valid length prefix but only half the payload and then close the socket: `readFully()` throws `EOFException`; no bogus message is returned.
- Send a partial frame and keep the socket open: the read can end with `SocketTimeoutException` after the wait duration.
- Have the peer send malformed UTF-8 bytes: the decoder with `REPORT` throws `CharacterCodingException`. If `new String(payload, UTF_8)` were used instead, the usual policy is to replace bad bytes, so corrupted data detection is not guaranteed.
- Split one frame across multiple `write()` calls or coalesce two frames into one `write()`: the receiver still separates them properly by reading according to length, proving framing is independent of TCP chunks.

## 9. Common Mistakes to Avoid

1. **Assuming one `write()` corresponds to one `read()`.** TCP is a byte stream; framing is mandatory.
2. **Reading once into a buffer and decoding immediately.** You may only receive part of a frame or half of a UTF-8 character.
3. **Writing `String.length()` as the frame length.** You must measure bytes after encoding with the agreed charset.
4. **Using the default charset.** This can produce different data across runtimes/machines; choose UTF-8 explicitly.
5. **Forgetting `flush()` after a frame when using buffered output.** The peer may wait for a request that has not been pushed down to the stream.
6. **Using `available()` to decide if a message is complete.** This is not an API for reading all data.
7. **Not bounding the length sent by a client.** This can cause excessive allocations or hang waiting for data that never arrives.
8. **Confusing EOF, timeout, and protocol errors.** They require different handling; mid-frame EOF is a corrupted frame.
9. **Closing one stream and trying to use the other stream of the same socket.** Usually the socket is already closed; use half-close or an appropriate protocol design.
10. **Letting multiple workers write to the same socket without coordination.** This can interleave frames and corrupt the protocol.
11. **Thinking a fixed thread pool bounds all load.** Queues and pending sockets still need limits.
12. **Retrying a request after a timeout without considering idempotency.** The server may have already finished processing before the client saw the timeout.

## 10. Checklist When Starting a Network Feature

- [ ] Is the protocol a TCP stream or UDP datagram? What defines message boundaries?
- [ ] Is length in bytes or characters? Are prefix, byte order, size limit, and malformed-frame policy defined?
- [ ] Is the charset explicitly specified (e.g., UTF-8), and are malformed bytes reported or replaced?
- [ ] Does the code handle partial reads/partial writes per the API, mid-frame EOF, and unprocessed buffer bytes?
- [ ] Are connect/read/accept timeouts and business deadlines clear? Are sockets closed on cancellation/error?
- [ ] Does buffered output flush at appropriate boundaries? Is competitive reading across wrappers avoided?
- [ ] Who owns each socket, buffer, and write stream? Are worker counts, connections, queues, and downstream load bounded?
- [ ] Are there tests for split/coalesced frames, Unicode payloads, malformed bytes, abnormal lengths, timeouts, resets, and concurrent clients?

Mastering these principles before diving into NIO, HTTP, TLS, or networking frameworks will help you reason accurately from bytes on the wire to the behavior of a concurrent Java application.
