# EOF, Closing Connections, and Half-Close in Java NIO Networking

## 1. The Problem: No Current Data Differs from End of Stream

In TCP networking, a connection carries **two independent directional byte streams**: client → server and server → client. When working with `java.nio.channels.SocketChannel`, you must distinguish three states:

- **No bytes ready to read right now**: in non-blocking mode, `read(ByteBuffer)` may return `0`; the connection may still receive data in the future.
- **The remote peer ended its sending direction normally**: after any pending data is consumed, `read(ByteBuffer)` returns `-1`, meaning *end of stream* (EOF) on the current receive direction.
- **The connection or channel errored/closed**: the call may throw `IOException` or a specific exception; never equate all such errors with normal EOF.

Java NIO allows closing the entire channel with `close()` or closing **one direction** (*half-close*) with `shutdownOutput()` / `shutdownInput()`. Choosing the wrong API can leave the server hanging forever, prevent the client from receiving a response, or truncate data.

Lesson goals: interpret `-1/0/>0` results accurately, understand TCP FIN, distinguish full close from half-close, write safe EOF-terminated request/response protocols, and handle lifecycle across blocking/non-blocking I/O.

## 2. What Does SocketChannel.read() Return?

With a `ByteBuffer` that still has space to receive data:

~~~java
int n = channel.read(buffer);
~~~

This is an illustrative call; `channel` must be a connected `SocketChannel` and `buffer` a valid buffer. Meaning of the result:

| Result | Meaning | Typically appropriate action |
| --- | --- | --- |
| `n > 0` | Received `n` bytes and `buffer.position()` advances accordingly | Process bytes and continue per protocol |
| `n == 0` | No bytes transferred in this call | In non-blocking mode: wait for next readiness; do not treat as EOF |
| `n == -1` | Receive direction reached **EOF**; no further bytes remain in that stream | Handle final frame, finish reading, or transition protocol state |
| Throws `IOException` | I/O error, abnormal disconnect, concurrent close, etc. | Handle error by type and clean up; do not convert into EOF |

**A buffer with no remaining space can also yield 0:** if `buffer.remaining() == 0`, `read` has nowhere to place bytes. Therefore ensure the buffer is in receive-ready state (typically after `clear()` or `compact()`). A `read` returning 0 when the buffer is full says nothing about TCP state.

In **blocking** mode, with buffer space available, `read` normally waits for data, EOF, or an error. In **non-blocking** mode, when no data is available yet, `read` can return `0` immediately. Never write `while (channel.read(buf) == 0) { }` to spin the CPU continuously; use `Selector` or a suitable coordinator.

EOF is a **directional** signal. When the server receives `-1` from the client, it means the client will send no more bytes on client → server; it does **not** mean the server lost the ability to send response data on server → client.

### EOF is not a special byte inside ByteBuffer

`-1` is the **return value of the read method**, not an `0xFF` byte inside the data. TCP carries arbitrary binary bytes, including `0xFF`, `0x00`, and empty sequences. Do not invent an "EOF byte" to insert into payloads expecting `SocketChannel.read` to recognize it automatically. At the socket level, EOF occurs because the connection's sending direction ended.

## 3. TCP Half-Close: shutdownOutput() Differs from close()

Visualize a bidirectional connection:

~~~text
Client                                   Server
   │ ---------- request bytes ----------> │
   │ ---------- FIN (write EOF) ---------> │
   │ <--------- response bytes ----------- │
   │ <--------- FIN (write EOF) ---------- │
   │                                       │
   └── close()                    close() ─┘
~~~

After the client finishes sending the request, `client.shutdownOutput()` ends **the client's write direction**. Under normal TCP operation, the server reads the entire request and then gets `-1`; yet the client can still read the response in the reverse direction. The server can do the same after sending the response.

Comparison:

| Method | Direction affected at caller | What can still be done afterward? |
| --- | --- | --- |
| `channel.shutdownOutput()` | Ends **writing** on this channel | Can still `read()` from peer; further `write()` throws `ClosedChannelException` |
| `channel.shutdownInput()` | Ends **reading** on this channel | Further reads return `-1`; can still `write()` if output is not shut down |
| `channel.close()` | Closes entire channel and its resources | No further read/write on channel; `isOpen()` becomes `false` |
| Peer calls `shutdownOutput()` | Peer stops sending into our read direction | Once pending bytes finish, our `read()` returns `-1`; can still write back |
| Peer closes connection normally | May see EOF once buffered data is read | Do not assume we can keep writing indefinitely; lifecycle ended on peer side |

**Core characteristic:** `shutdownOutput()` does not close the entire `SocketChannel`. After a successful call, `channel.isOpen()` can still be `true`. "Channel is still open" does not equate to "both directions still allow reading/writing".

Calling `shutdownOutput()` again when output is already shut down has no effect. However, if the channel is already fully closed, `shutdownOutput()` throws `ClosedChannelException`; if not yet connected, it can throw `NotYetConnectedException`.

Distinguish **stream termination signaling** from **business-level confirmation**. TCP FIN follows the bytes the sender handed down to the TCP stack in order; it is not confirmation that the server processed the request, wrote to a database, or committed a transaction. For completion confirmation, the application protocol needs its own explicit response.

## 4. Complete Java 17+ Example: Send Request, Half-Close, Read Response

The example opens a `ServerSocketChannel` on loopback with an ephemeral port (port 0), requiring no external server and reducing port conflicts. The client sends `ping`, calls `shutdownOutput()`, waits for the server to read until EOF and reply `pong`. The server also calls `shutdownOutput()` so the client sees EOF for the response.

Create file `HalfCloseDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class HalfCloseDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<?> task = executor.submit(() -> {
                    try (SocketChannel peer = listener.accept()) {
                        String request = readUntilEof(peer, "Server");
                        System.out.println("Server request: " + request);
                        writeAll(peer, "pong");
                        peer.shutdownOutput();
                    } catch (IOException ex) {
                        throw new UncheckedIOException(ex);
                    }
                });

                try (SocketChannel client = SocketChannel.open()) {
                    client.connect(listener.getLocalAddress());
                    writeAll(client, "ping");
                    client.shutdownOutput();
                    String response = readUntilEof(client, "Client");
                    System.out.println("Client response: " + response);
                }
                task.get();
            } finally {
                executor.shutdownNow();
            }
        }
    }

    private static void writeAll(SocketChannel channel, String text)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.wrap(text.getBytes(StandardCharsets.UTF_8));
        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }

    private static String readUntilEof(SocketChannel channel, String side)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.allocate(16);
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        while (true) {
            int n = channel.read(buffer);
            if (n == -1) {
                System.out.println(side + " EOF: -1");
                break;
            }
            if (n == 0) {
                continue;
            }
            buffer.flip();
            byte[] part = new byte[buffer.remaining()];
            buffer.get(part);
            bytes.write(part);
            buffer.clear();
        }
        return bytes.toString(StandardCharsets.UTF_8);
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac HalfCloseDemo.java
java HalfCloseDemo
~~~

Exact output verified by compiling and running:

~~~text
Server EOF: -1
Server request: ping
Client EOF: -1
Client response: pong
~~~

**Lifecycle explanation:**

1. The listener binds to loopback; `listener.getLocalAddress()` returns the actual address/port for the client to connect to. Both `SocketChannel` instances default to blocking mode.
2. A task on a separate thread calls `listener.accept()` to obtain the server socket. `Future.get()` at the end lets the main thread wait for the server to finish and propagates server task errors back to the main thread.
3. The client calls `writeAll` to ensure the `ByteBuffer` is completely consumed by the channel; `write` **may write fewer bytes than remain**, so it must loop until `hasRemaining()` is false.
4. `client.shutdownOutput()` signals the end of the sending direction. The server's `readUntilEof` reads all bytes; it stops only when `read` returns `-1`, then prints the request `ping`.
5. The server can still call `writeAll(peer, "pong")` even though its receive direction hit EOF. That is the benefit of half-close. After sending the response, the server calls `shutdownOutput()`.
6. The client receives `pong` and reads until EOF in the reverse direction. Finally `try-with-resources` closes both `SocketChannel` instances and the listener.
7. The example illustrates only a **single-request, single-response protocol terminated by EOF**; not a protocol that reuses the same connection across multiple rounds.

`readUntilEof` collects bytes before decoding UTF-8. This prevents a multi-byte character from being split across two `read` calls. For large payloads, avoid buffering everything in memory: decode UTF-8 in streaming mode or write directly to a bounded file/consumer.

The `n == 0` branch in the example does not busy-spin in normal operation because the channel is in blocking mode with buffer space available. **Do not copy this loop verbatim into non-blocking mode**; use `Selector` and manage readiness instead.

## 5. shutdownInput(): Stopping Local Reads

`channel.shutdownInput()` stops **the channel's own read direction** without necessarily closing the write direction. Per the `SocketChannel` API, after shutting down input, subsequent `read` calls return `-1`. If another thread is blocked inside `read` on the same channel, the operation wakes up and completes with `-1` per the `SocketChannel` contract.

Illustrative snippet when `channel` is already connected:

~~~java
channel.shutdownInput();
int n = channel.read(ByteBuffer.allocate(8));
System.out.println(n); // -1
~~~

This is only an illustrative snippet that must sit inside a method handling `IOException`.

What **must not be misunderstood**: calling `shutdownInput()` on the client is not a signal to the server saying "I finished sending my request". For the server to observe EOF on the **client-to-server stream**, the client calls `shutdownOutput()`. `shutdownInput()` is a local read-state change; unread data may be discarded in a platform-dependent manner, and applications should not use it expecting to "drain and resume" that same direction later.

If a client intentionally refuses further responses by shutting down input while the server is still writing, network consequences vary by platform. Never assume the server will always be notified immediately or that server writes are guaranteed to succeed.

## 6. Closing the Entire Channel: close() Is Not Half-Close

`channel.close()` closes the channel resource. In code using `try-with-resources`, `close()` is called on block exit even if an exception occurs. Full close is the right choice when the application **no longer needs to read or write** on the connection.

~~~java
try (SocketChannel channel = SocketChannel.open(address)) {
    // Complete request/response exchange per protocol.
} // close() here
~~~

This is an illustrative snippet inside a method with a valid `address` and exception handling. Typical teardown sequence:

1. Finish sending application data; if the protocol requires a request-end marker on the write side, write the marker/length or call `shutdownOutput()` per protocol contract.
2. If a response is still needed, keep reading until the full response arrives per protocol—either by declared byte count or server EOF.
3. Only when no further data is needed, close the entire channel with `close()`.

If a client calls `close()` **immediately after writing a request** in a protocol expecting a response, the client loses its ability to read the response. Depending on socket state, OS, and buffered data, the peer may observe EOF or a reset error; never guarantee that "close will always send FIN and every byte will arrive".

Common exceptions/phenomena when closing:

- When one thread is blocked in an I/O operation and another thread closes the channel, the operation may fail with `AsynchronousCloseException`.
- If a thread blocked in I/O is interrupted, the channel closes and throws `ClosedByInterruptException` per the `InterruptibleChannel` contract.
- After full close, `isOpen()` is `false`; I/O operations can no longer continue and typically throw `ClosedChannelException`.
- `shutdownOutput()` closes only the write direction: subsequent writes throw `ClosedChannelException` **even while `isOpen()` remains true**.
- A TCP reset from the peer may appear as `SocketException`/`IOException` instead of EOF; log the error type and protocol state.

Unlike a connected `SocketChannel`, `ServerSocketChannel` is a **connection-accepting listener**. It has no "request-send and response-receive directions" on a single connection; use `close()` to stop accepting and release the listener.

## 7. EOF in Blocking and Non-blocking I/O

### 7.1. Standard blocking read loop

With a blocking channel and properly prepared buffer:

~~~java
ByteBuffer buf = ByteBuffer.allocate(4096);
while (true) {
    int n = channel.read(buf);
    if (n == -1) {
        break; // EOF: peer ended its sending direction.
    }
    if (n == 0) {
        continue; // Do not treat as EOF.
    }
    buf.flip();
    // Consume bytes in [position, limit) of buf.
    buf.clear();
}
~~~

This is an **illustrative snippet**, not a standalone program. Replace the "consume" comment with real processing before `clear()`. `clear()` only resets pointers and **does not erase data**. If a decoder received less than a full frame, call `compact()` to retain leftover bytes rather than discarding them.

### 7.2. State machine with Selector

In non-blocking mode, a `SelectionKey.OP_READ` event can mean **data is available to read or EOF/error state has arrived**. The handler must call `channel.read(...)` and branch on the return value, never treating readiness as proof that `n > 0`.

Conceptual control pattern:

~~~java
if (key.isReadable()) {
    SocketChannel ch = (SocketChannel) key.channel();
    int n = ch.read(receiveBuffer);
    if (n > 0) {
        // Decode / accumulate frame; wait for next event if incomplete.
    } else if (n == 0) {
        // No bytes yet: return to selector, do not busy-spin.
    } else { // n == -1
        key.interestOps(key.interestOps() & ~SelectionKey.OP_READ);
        // Mark input EOF; handle final request/pending response.
        // Only close the channel once both directions are complete.
    }
}
~~~

This is **event-loop illustrative code**, assuming `key` is valid, `receiveBuffer` is prepared, and exceptions are handled externally. `SelectionKey` and `SocketChannel` can be imported from `java.nio.channels`.

If `OP_READ` stays enabled after EOF and the loop keeps reading immediately without changing state, many systems keep reporting the channel ready continuously, causing high CPU usage. You must **stop reading interest**, finish receive-side handling, or close the connection once the remaining send direction finishes.

With non-blocking `write`, `n == 0` is likewise neither an error nor "finished sending"; typically keep the buffer with `hasRemaining()` and wait for `OP_WRITE` while outbound data awaits. Do not leave `OP_WRITE` registered when no bytes need sending, because sockets can stay continuously writable.

### 7.3. The parser must distinguish EOF from the final frame

TCP is a **byte stream** and does not preserve individual `write` boundaries as individual `read` calls. One `"hello"` request may arrive across many reads; many requests may arrive inside one read.

When EOF arrives:

- If the protocol is based on "read until sender closes output", EOF marks a valid end of payload.
- If the protocol uses fixed length/length-prefix and EOF arrives with missing bytes, report a **truncated frame** rather than accepting partial data as a valid request.
- If the protocol supports multiple frames over a long-lived connection, EOF generally indicates the peer ended its sending direction, **not** a separator between prior frames; the parser must still respect protocol boundaries.
- Without EOF or a delimiter/length-prefix, the server cannot reliably know a request has ended merely because a `read` returned `0` or the client paused sending.

Never use `buffer.hasRemaining()`, `channel.isConnected()`, or `channel.isOpen()` as a substitute for `read() == -1` to check whether the peer sent EOF.

## 8. Why Do Server or Client Hang While Waiting for EOF?

Consider a protocol like "client sends entire request, server waits for EOF then sends response". If the client behaves like:

~~~text
Client: write(request) → read(response)
Server: readUntilEOF(request) → write(response)
~~~

both sides can **wait on each other forever**:

- The client is waiting for the response so it never ends its send direction.
- The server is waiting for request EOF so it never produces the response.

Fix using half-close:

~~~text
Client: write(request) → shutdownOutput() → read(response)
Server: readUntilEOF(request) → write(response) → shutdownOutput()
~~~

Another approach is designing **framing that needs no half-close**:

~~~text
[4 bytes length][N bytes request] → server knows to read exact N bytes
[4 bytes length][M bytes response] → client knows to read exact M bytes
~~~

Length-based framing lets a connection be reused for multiple requests/responses, pipelining, or multiplexing. Half-close fits protocols with **a truly finite one-way stream**, where nothing further will ever be sent in that direction. If the client needs to send a second request after receiving the first response, **do not** call `shutdownOutput()` after the first request on the same socket.

### Timeouts and cancellation

A production client/server should never wait indefinitely when a peer fails to send a complete frame or never half-closes. With `Selector`, manage deadlines and cancel registrations/close channels on expiry; with blocking channels, enforce appropriate timeout/cancellation policies (thread interruption, coordinated channel closure, or higher-level mechanisms). Do not assume `Socket.setSoTimeout(...)` applies identically as a timeout for every `SocketChannel.read(...)` call; choose timeout mechanisms suited to your mode and application architecture.

## 9. Shutdown and Races Between Threads

Per the Java API, `SocketChannel` can be used concurrently by threads for reading and writing, with **at most one reading thread and one writing thread at a time**. If thread A is inside `read()` and thread B calls `shutdownInput()`, the blocked read wakes up and returns `-1`. If thread A is inside `write()` and B calls `shutdownOutput()`, the blocked write may terminate with `AsynchronousCloseException` per contract.

These APIs manage directional lifecycle; they **do not** make a shared `ByteBuffer` thread-safe. If reader and writer share a buffer or multiple workers modify `position/limit` of the same buffer, you still need strict ownership or synchronization.

Ownership recommendations:

- Each connection has a lifecycle coordinator tracking `OPEN`, `OUTPUT_SHUTDOWN`, `INPUT_EOF`, and `FULLY_CLOSED` states as needed; send/receive states can combine and occur in different orders.
- Call `shutdownOutput()` **only after all outbound bytes have been accepted by the channel**; in non-blocking I/O, retain remaining writes rather than treating "called write once" as completion.
- Reading tasks must be notified if output or the whole connection is about to close when task results depend on a response.
- Call `close()` only when no critical pending read/write remains, or when intentionally aborting them and accepting cancellation errors.
- After receiving EOF, the receive direction has ended; if the application still needs to send a response, do not automatically full-close inside the EOF-handling callback.

Ensure cleanup uses `try-with-resources`, `finally`, or equivalent lifecycle management. When cancelling multiple async tasks, avoid double-close bugs and paths that might leak selectors/keys/channels.

## 10. Normal EOF, Reset, Timeout, and Exceptions

| Observation | Should NOT be interpreted as | Suggested handling |
| --- | --- | --- |
| `read() == -1` | Not "no data yet" | Mark peer done sending in that direction; finalize message |
| `read() == 0` | Not EOF | Check buffer remaining space, blocking/non-blocking mode, wait for readiness |
| `ClosedChannelException` | Not proof the peer sent FIN | Check whether our own code closed/shut down output or closed concurrently |
| `AsynchronousCloseException` | Not always a network error | Check whether another thread closed/shut down during blocked I/O |
| `ClosedByInterruptException` | Not FIN from peer | Check interruption/cancellation policy |
| `SocketException: Connection reset` (platform-dependent message) | Not normal EOF | Handle peer/network error; do not assume payload completed |
| Flushed entire buffer with `write()` | Does not prove peer received and processed | Require application-layer acknowledgment if business logic demands it |
| `channel.isOpen() == true` | Does not prove both directions remain active | Track input/output and protocol states independently |

A connection reset (RST), severed network, crashed peer, or TLS failure may not produce a clean EOF. Distinguishing graceful EOF from exceptional termination is critical when updating business state: never mark a transaction "completed successfully" unless payload framing and checksums/application acknowledgments are satisfied.

## 11. Notes on TLS and Higher-Level Protocols

Examples in this lesson use **raw TCP**. With TLS, application-level closing semantics also involve TLS `close_notify` and `SSLEngine`/TLS library mechanics. Never treat a raw TCP FIN as proof that a valid TLS close message was received. Closing without `close_notify` constitutes *truncation* for some protocols; applications must obey both the encryption-layer and protocol contracts.

Similarly, HTTP uses Content-Length/chunked framing and connection persistence rules; you cannot determine "entire HTTP response received" solely by waiting for TCP EOF in all cases. Use the protocol's framing/parser instead of assuming connection closure after every message.

## 12. Common Mistakes and How to Avoid Them

1. **Treating `read() == 0` as closed:** non-blocking 0 only means no bytes were available in that read, or the buffer had no room.
2. **Ignoring `-1` and keeping `OP_READ` registered:** easily creates a readiness/EOF loop and burns CPU.
3. **Waiting for EOF without calling `shutdownOutput()` when the protocol requires it:** creates a deadlock where client waits for response while server waits for request end.
4. **Calling `close()` right after sending a request that expects a response:** loses the ability to read the reverse direction.
5. **Calling `shutdownInput()` to tell the server the request is done:** wrong direction; use `shutdownOutput()`.
6. **Calling `shutdownOutput()` and then trying to send more data:** output is shut down, so further writes throw `ClosedChannelException`.
7. **Assuming one `write` sends everything or one `read` gets a full message:** TCP does not preserve message boundaries; use read/write loops and framing.
8. **Using half-close for multi-request protocols on one direction:** once output is shut down, that sending direction cannot be reopened on the same channel.
9. **Treating TCP EOF as business success:** EOF only indicates the network send direction ended; validate payload and application responses.
10. **Failing to enforce size limits/deadlines:** a peer can send oversized data or never terminate; production requires resource bounds and timeouts.

## 13. Self-Check Questions

1. In non-blocking mode, does `read(buffer) == 0` prove the server closed the connection? **No**, that call simply received no bytes (or the buffer had no space), not EOF.
2. A client sends a request and calls `shutdownOutput()`. Can the client still read the response? **Yes**, because only the client's write direction was closed.
3. The server reads `-1`, yet still needs to return a computed result. Can it call `write()`? **Yes**, provided the server's write direction is still open and the connection is not closed/errored.
4. Why doesn't `shutdownInput()` replace `shutdownOutput()` to signal request EOF to the server? Because `shutdownInput()` stops the **local receive direction**, whereas the server is waiting for the end of the **client's send direction**.
5. After `shutdownOutput()`, `isOpen()` can still be true, but does `write()` work? **No**, further writes throw `ClosedChannelException`.
6. Client and server both call `readUntilEOF()` without either closing output: what happens? **They can wait on each other forever**, unless the protocol or a cancellation/timeout breaks the deadlock.
7. Does EOF always occur if a network cable is cut or the peer process is killed? **No**. Timeouts, resets, or `IOException` may occur; or there may be no immediate signal at all.
8. A `SocketChannel.read()` call returns 5 bytes. Does that mean the peer sent a single 5-byte message? **No**. TCP is a byte stream; 5 bytes may be part of one message or span parts of multiple messages.
9. If the server sends a response using length-prefix framing, must the client always wait for `-1` to finish reading the response? **No**. It can finish once the full frame matching the declared length has been received.
10. When using `Selector`, upon receiving `-1`, should you keep `OP_READ` enabled and read repeatedly forever? **No**. Transition state and clear read interest or close when appropriate.

## API References

- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): `read`, `write`, `shutdownInput`, `shutdownOutput`, thread concurrency, and connections.
- [Java SE 17 — ReadableByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ReadableByteChannel.html): meaning of read return values `n > 0`, `0`, `-1`.
- [Java SE 17 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): bind, accept, and closing listeners.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `OP_READ`, `OP_WRITE`, selection state.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `clear`, `compact`, and buffer operations.
