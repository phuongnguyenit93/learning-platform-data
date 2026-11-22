# Java NIO.2: Chaining accept, read, processing, and write without losing state

## 1. The problem: asynchronous I/O does not mean “forgetting” the work in progress

A TCP server needs to **accept connections**, **read requests**, **process business logic**, and **write responses**. When using Java NIO.2 (`AsynchronousServerSocketChannel`, `AsynchronousSocketChannel`), these operations are **initiated asynchronously**: the call submits the I/O request to the runtime and returns control, and **the result arrives later** via a `CompletionHandler` or `Future`. Therefore, the program cannot assume that adjacent statements will automatically execute in the order of I/O completion.

The correct processing flow for a request:

~~~text
server.accept(...)
      |
      | accept completed: client's AsynchronousSocketChannel is available
      v
New Session (per-connection state)
      |
      v
read HEADER [read until 4 bytes] --partial--> continue reading into the same ByteBuffer
      |
      v
validate length, allocate PAYLOAD buffer
      |
      v
read PAYLOAD [read until length bytes] --partial--> continue reading
      |
      v
process the complete message
      |
      v
write RESPONSE [write the entire buffer] --partial--> continue writing
      |
      v
cleanup; close connection or transition state to read next request
~~~

**Meaning of “chaining”:** only start a dependent step when the previous step's callback confirms that the required data is complete. **Meaning of “without losing state”:** preserve the session object, `ByteBuffer.position()`, length, phase, outbound buffer, and socket ownership across callbacks; do not recreate the data every time a callback runs.

This article targets TCP servers with **Java 17+** and NIO.2. After reading it, you will understand and be able to write an accept → read → process → write pipeline, know how to re-arm accept, and handle partial transfers, EOF, errors, timeouts, cleanup, and load limits. The complete code example uses an asynchronous server and a standard test client over loopback.

## 2. Two kinds of “asynchronous” to distinguish

### 2.1. Non-blocking NIO + Selector

`SocketChannel.configureBlocking(false)` with `Selector` is a **readiness** model: you are notified that a channel is ready for I/O and then call `read/write`; the result may be `0` if no progress is made yet. The application directly manages the event loop and `SelectionKey.OP_READ/OP_WRITE`.

### 2.2. NIO.2 AsynchronousSocketChannel

`AsynchronousSocketChannel` is a **completion** model: you call `channel.read(buffer, attachment, handler)`, and then the runtime invokes `handler.completed(result, attachment)` when the operation finishes, or `handler.failed(error, attachment)` when it fails. The application writes the next step inside the callback without having to call `Selector.select()` itself.

| Criterion | NIO + Selector | NIO.2 Asynchronous channels |
| --- | --- | --- |
| Accepting connections | `ServerSocketChannel.accept` after OP_ACCEPT | `AsynchronousServerSocketChannel.accept` + handler |
| Reading | `SocketChannel.read` on OP_READ | `AsynchronousSocketChannel.read` + completion callback |
| Writing | `SocketChannel.write` on OP_WRITE | `AsynchronousSocketChannel.write` + completion callback |
| Result | Returned at call time | Returned later via callback or `Future` |
| In-progress work | Buffer, parser state, outbound queue | Buffer, parser state, session state attached to callback |
| Handler thread | Organized by the application's event loop | Organized by the asynchronous channel provider's I/O thread pool |
| Can partial I/O occur? | Yes | Yes |
| Need deadlines/load limits? | Yes | Yes |

**Do not mix APIs** arbitrarily: `AsynchronousSocketChannel` does not have `register(selector, ...)` to be used like `SocketChannel`; conversely, calling `SocketChannel.read` does not mean a completion callback will be dispatched automatically.

## 3. APIs for building the accept → read → write chain

### 3.1. Asynchronous accept

~~~java
AsynchronousServerSocketChannel server =
        AsynchronousServerSocketChannel.open()
                .bind(new InetSocketAddress("127.0.0.1", 0));

server.accept(state, new CompletionHandler<
        AsynchronousSocketChannel, ServerState>() {
    @Override
    public void completed(AsynchronousSocketChannel peer,
                          ServerState attachment) {
        // peer is the successfully accepted socket.
        // Hand it over to a Session and start reading.
    }

    @Override
    public void failed(Throwable error, ServerState attachment) {
        // Accept error or shutdown; handle appropriately.
    }
});
~~~

This is an **illustrative snippet**: `ServerState` is an application-defined class not declared in the snippet above. If an `accept` does not complete, there is **no** client socket ready to read. The callback form of `accept(...)` returns immediately without returning an `AsynchronousSocketChannel` directly. That result appears in `completed`.

A listening channel can only have **one pending accept** at a time; calling `accept` again while an accept has not completed can throw `AcceptPendingException`. To continue accepting other connections after a successful accept, **register a new accept** inside the completion callback, provided the server is still running.

### 3.2. Asynchronous read

~~~java
// peer is the accepted AsynchronousSocketChannel.
// header is a ByteBuffer allocated with 4 bytes.
// attachment can be the Session object.
peer.read(header, attachment, new CompletionHandler<Integer, Session>() {
    @Override
    public void completed(Integer n, Session session) {
        // n: number of bytes read, or -1 if EOF.
        // If header still has remaining, continue reading; do not decode yet.
    }

    @Override
    public void failed(Throwable error, Session session) {
        // Cleanup session, log, report error.
    }
});
~~~

This is also **illustrative code**. The `AsynchronousSocketChannel.read` callback overload returns `void`; `Integer n` in `completed` is the result of **a single read operation**, which is not guaranteed to contain enough data for a 4-byte field. If the stream ends, `n == -1`; if the destination buffer has no space left or an operation completes without transferring bytes, `n == 0` is not EOF. Always check `buffer.hasRemaining()` and the protocol state.

While a `read` is still pending, **do not initiate a second read on the same channel**: you may encounter `ReadPendingException`. In a simple pipeline, only re-arm read **from the `completed` callback** of the previous one, ensuring there is always at most one pending read operation.

### 3.3. Asynchronous write

~~~java
// reply is already in read mode: position points to the first unwritten byte.
peer.write(reply, attachment, new CompletionHandler<Integer, Session>() {
    @Override
    public void completed(Integer n, Session session) {
        // n is the number of bytes written in this call.
        // If reply.hasRemaining(), continue writing.
    }

    @Override
    public void failed(Throwable error, Session session) {
        // Cleanup session, do not blindly retry the whole frame.
    }
});
~~~

`write` may complete only partially, and `ByteBuffer.position()` advances automatically by the number of bytes accepted by the channel for sending. There is no `-1` sentinel for write operations like there is for reads. If a write is still pending, a second write may throw `WritePendingException`; **do not let multiple callbacks write concurrently on the same socket** without serializing the data.

### 3.4. What is Attachment for?

Typical signature:

~~~java
<A> void read(ByteBuffer dst,
              A attachment,
              CompletionHandler<Integer, ? super A> handler)
~~~

The `attachment` parameter lets you pass the **context of an operation/connection** into both the success and failure branches. For example, a `Session` containing the socket, header, payload, response, request ID, and current state. You can also use an inner class or a lambda capturing final/effectively-final variables, but an explicit Session object is usually easier to extend.

**Note:** the attachment is not where the runtime automatically stores message boundaries. It is simply an object you supply; the application must manage `position`/`limit`, phase, and lifecycle properly.

## 4. Rules for managing per-connection state

For a multi-client server, strictly avoid global variables like `static ByteBuffer requestBuffer` where all clients write into it. Each session should have its own state:

| Field | Role |
| --- | --- |
| `AsynchronousSocketChannel peer` | The owned connection |
| `ByteBuffer header` | 4-byte length being received / received |
| `ByteBuffer payload` | Request data being received |
| `ByteBuffer response` | Response data waiting to be written |
| `Phase READ_HEADER / READ_PAYLOAD / WRITING / DONE` | Current step |
| `requestId`, principal, and deadline | Application context if needed |
| `closed`, `complete` | Prevent duplicate cleanup/reply |

Principles:

1. **One `Session` per connection.** Client A's callback only updates Client A's buffer, never using B's buffer.
2. **Only transition phase when enough bytes are present.** Header requires 4 bytes; payload requires the exact validated length; response is only complete when `!response.hasRemaining()`.
3. **Do not reset the ByteBuffer between partial completions.** `read`/`write` update position automatically. Call `flip()` after receiving the full data or after building the full response, **do not flip again after each chunk**.
4. **One pending read and one pending write are operations with separate contracts.** For a simple request-response pipeline, there is no need to run multiple concurrent I/Os in the same direction.
5. **Callbacks must not be assumed to always run on the same thread.** State should have a single logical owner; if multiple other threads also access the session, synchronization/actor mailbox/event queue is required.
6. **Both success and failure paths must clean up resources.** An exception after accept must not leak the peer socket or leave a session stuck in an incomplete phase.

Do not confuse *asynchronous* with *thread-safe*: callback-based APIs do not automatically protect every collection/field shared among client handlers.

## 5. After accept completes, continue accepting properly

A server that calls `accept` only once will serve only one connection. After each successful accept, if still serving, issue the next accept **before or independently of** starting to process the newly accepted peer:

~~~java
// Java pseudocode, assuming server is open and running is true.
void acceptNext() {
    server.accept(null, new CompletionHandler<
            AsynchronousSocketChannel, Void>() {
        @Override
        public void completed(AsynchronousSocketChannel peer,
                              Void unused) {
            if (running) {
                acceptNext();  // Re-arm for the next connection.
            }
            new Session(peer).readHeader();
        }

        @Override
        public void failed(Throwable error, Void unused) {
            if (running) {
                // Log and decide to retry/backoff or stop the server.
            }
        }
    });
}
~~~

This is **pseudocode with self-defined variables/classes**, not a standalone program. It illustrates how to **re-arm** accept when there is no longer a pending accept. In a real service, you must also:

- Check `running` in a thread-safe manner and handle races between shutdown/close and the accept callback.
- Handle the case where `acceptNext()` or creating/starting the Session throws an exception (close `peer` immediately).
- Avoid infinite immediate retries on repeated listener errors; use backoff or stop.
- Limit the total number of connections using a connection cap/semaphore to avoid creating unbounded Sessions when clients arrive in bursts.
- If the server is shut down, a socket accepted right around shutdown time must still be handed off properly or closed immediately; do not abandon it.

Do not start a **second** accept while the first accept is still pending. The right place to call it again is inside the `completed` callback of the finished accept, or via a coordination mechanism ensuring only one accept is in-flight.

## 6. From callbacks to a provably correct “state machine”

A connection needs to receive a `4-byte big-endian length + N-byte payload` frame, process the text, and send a similar response frame. State machine:

~~~text
ACCEPTED
    |
    v
READ_HEADER [header.position < 4]
    | read n > 0, still short ----> READ_HEADER (same buffer)
    | read -1 --------------------> FAIL: EOF in header
    | 4 bytes reached
    v
VALIDATE_LENGTH [0 <= N <= MAX_FRAME]
    | invalid --------------------> FAIL: malformed frame
    | valid
    v
READ_PAYLOAD [payload.position < N]
    | read n > 0, still short ----> READ_PAYLOAD (same buffer)
    | read -1 --------------------> FAIL: truncated payload
    | N bytes reached
    v
PROCESS
    | build response ONCE
    v
WRITE_RESPONSE [response.hasRemaining()]
    | partial write --------------> WRITE_RESPONSE (same buffer)
    | write failed ---------------> FAIL
    | no remaining
    v
DONE: close socket or return to READ_HEADER for next request
~~~

This is the **logical order**; callbacks may run on different worker threads. What matters is that **the re-read function uses the exact existing buffer field**, without allocating a new header buffer when the header has only received 1–3 bytes.

### 6.1. Header and payload have no boundaries in TCP

Suppose the request is:

~~~text
00 00 00 05 | 68 65 6C 6C 6F
length = 5 | UTF-8/ASCII "hello"
~~~

The result of a single `read(header)` may be only 1, 2, 3, or 4 bytes. Only after all 4 bytes are present can `header.flip()` and `header.getInt()` read `length=5`. The payload may also arrive as 2+3 or 1+1+3 bytes. `AsynchronousSocketChannel` does not guarantee that every read fills the entire `ByteBuffer`.

### 6.2. Buffer position is progress

For example, with a 4-byte header, the first callback reads 2 bytes:

~~~text
Before read:
header.position=0; limit=4; remaining=4

completed(n=2):
header.position=2; limit=4; remaining=2
=> call peer.read(header, ...) next, DO NOT flip, DO NOT clear.

Next completed(n=2):
header.position=4; limit=4; remaining=0
=> header.flip(); getInt() => complete length.
~~~

For the response, `write` also advances position by the number of bytes written:

~~~text
9-byte response: [4-byte header][5-byte payload]
write completed(n=3) -> position=3, remaining=6
write completed(n=6) -> position=9, remaining=0
=> all sent to the channel; only now close/wait for the next request.
~~~

**Do not call `response.flip()` again after a partial write.** Doing so may re-send the beginning. **Do not initiate multiple writes at the same time** on the same session to “speed up”: there is also `WritePendingException` and the risk of interleaving frames from producers.

## 7. Complete Java 17+ example: chaining accept → read header → read payload → process → write

This is a **self-contained demo over loopback**, requiring no external server. The server uses `AsynchronousServerSocketChannel` and `AsynchronousSocketChannel` with `CompletionHandler`. Two test clients use blocking `java.net.Socket` to keep the test code easy to follow without changing the **asynchronous nature of the server**.

Demo protocol:

- **Request:** 4-byte big-endian `int` specifying length N (1..1,024), followed by N ASCII bytes.
- **Processing:** convert the ASCII request to uppercase using `Locale.ROOT`.
- **Response:** 4-byte big-endian length, followed by the ASCII response.
- **Lifecycle:** the server accepts **2 clients**, re-arming accept before processing the first client; each Session has its own buffers; reads completely, writes completely, closes peer, and counts completions.

A fixed number of clients gives the example a deterministic endpoint and stdout; a production server will have an accept loop continuing until shutdown, a connection limiter, and its own retry/timeout policies.

Create the file **AsyncChainDemo.java** with the following content:

~~~java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class AsyncChainDemo {
    static final int CLIENTS = 2;
    static final int MAX_BYTES = 1024;

    static void acceptNext(
            AsynchronousServerSocketChannel server,
            AtomicInteger accepted,
            AtomicInteger handled,
            CompletableFuture<Void> all) {

        server.accept(null,
                new CompletionHandler<AsynchronousSocketChannel, Void>() {
            @Override
            public void completed(AsynchronousSocketChannel peer,
                                  Void unused) {
                try {
                    if (accepted.incrementAndGet() < CLIENTS) {
                        // Re-arm accept BEFORE processing the newly accepted peer.
                        acceptNext(server, accepted, handled, all);
                    }
                    new Session(peer, handled, all).readHeader();
                } catch (Throwable error) {
                    try {
                        peer.close();
                    } catch (IOException closeError) {
                        error.addSuppressed(closeError);
                    }
                    all.completeExceptionally(error);
                }
            }

            @Override
            public void failed(Throwable error, Void unused) {
                all.completeExceptionally(error);
            }
        });
    }

    static final class Session {
        final AsynchronousSocketChannel peer;
        final AtomicInteger handled;
        final CompletableFuture<Void> all;

        // Do not recreate buffers after a partial completion.
        final ByteBuffer header = ByteBuffer.allocate(4);
        ByteBuffer payload;
        ByteBuffer response;

        Session(AsynchronousSocketChannel peer,
                AtomicInteger handled,
                CompletableFuture<Void> all) {
            this.peer = peer;
            this.handled = handled;
            this.all = all;
        }

        void readHeader() {
            peer.read(header, null, new CompletionHandler<Integer, Void>() {
                @Override
                public void completed(Integer n, Void unused) {
                    try {
                        if (n == -1) {
                            fail(new EOFException("EOF in header"));
                            return;
                        }

                        if (header.hasRemaining()) {
                            // Read 1..3 bytes? Continue reading into the same header.
                            readHeader();
                            return;
                        }

                        header.flip();
                        int length = header.getInt();
                        if (length < 1 || length > MAX_BYTES) {
                            fail(new IOException("Invalid length " + length));
                            return;
                        }

                        payload = ByteBuffer.allocate(length);
                        readPayload();
                    } catch (Throwable error) {
                        fail(error);
                    }
                }

                @Override
                public void failed(Throwable error, Void unused) {
                    fail(error);
                }
            });
        }

        void readPayload() {
            peer.read(payload, null, new CompletionHandler<Integer, Void>() {
                @Override
                public void completed(Integer n, Void unused) {
                    try {
                        if (n == -1) {
                            fail(new EOFException("EOF in payload"));
                            return;
                        }

                        if (payload.hasRemaining()) {
                            // Continue reading missing bytes, preserving position.
                            readPayload();
                            return;
                        }

                        payload.flip();
                        byte[] data = new byte[payload.remaining()];
                        payload.get(data);

                        byte[] answer = new String(
                                data, StandardCharsets.US_ASCII)
                                .toUpperCase(Locale.ROOT)
                                .getBytes(StandardCharsets.US_ASCII);

                        response = ByteBuffer.allocate(4 + answer.length);
                        response.putInt(answer.length);
                        response.put(answer);
                        response.flip();
                        writeResponse();
                    } catch (Throwable error) {
                        fail(error);
                    }
                }

                @Override
                public void failed(Throwable error, Void unused) {
                    fail(error);
                }
            });
        }

        void writeResponse() {
            peer.write(response, null, new CompletionHandler<Integer, Void>() {
                @Override
                public void completed(Integer n, Void unused) {
                    try {
                        if (response.hasRemaining()) {
                            // May have written only partially; keep buffer.
                            writeResponse();
                            return;
                        }

                        // Complete only after all bytes have been written.
                        peer.close();
                        if (handled.incrementAndGet() == CLIENTS) {
                            all.complete(null);
                        }
                    } catch (Throwable error) {
                        fail(error);
                    }
                }

                @Override
                public void failed(Throwable error, Void unused) {
                    fail(error);
                }
            });
        }

        void fail(Throwable error) {
            try {
                peer.close();
            } catch (IOException closeError) {
                error.addSuppressed(closeError);
            }
            all.completeExceptionally(error);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open()
                             .bind(new InetSocketAddress(
                                     InetAddress.getLoopbackAddress(), 0))) {

            int port =
                    ((InetSocketAddress) server.getLocalAddress()).getPort();
            AtomicInteger accepted = new AtomicInteger();
            AtomicInteger handled = new AtomicInteger();
            CompletableFuture<Void> all = new CompletableFuture<>();

            acceptNext(server, accepted, handled, all);

            // Blocking test client; server still uses NIO.2 async.
            for (String request : List.of("hello", "nio2")) {
                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            InetAddress.getLoopbackAddress(), port), 2_000);
                    client.setSoTimeout(3_000);

                    DataOutputStream out =
                            new DataOutputStream(client.getOutputStream());
                    DataInputStream in =
                            new DataInputStream(client.getInputStream());

                    byte[] data =
                            request.getBytes(StandardCharsets.US_ASCII);
                    out.writeInt(data.length);
                    out.write(data);
                    out.flush();

                    int replyLength = in.readInt();
                    if (replyLength < 1 || replyLength > MAX_BYTES) {
                        throw new IOException("Invalid reply length");
                    }
                    byte[] reply = in.readNBytes(replyLength);
                    if (reply.length != replyLength) {
                        throw new EOFException("Short reply");
                    }

                    System.out.println("reply: " + new String(
                            reply, StandardCharsets.US_ASCII));
                }
            }

            // Wait FROM main, do not block a completion handler.
            all.get(5, TimeUnit.SECONDS);
            System.out.println("handled: " + handled.get());
        }
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 AsyncChainDemo.java
java AsyncChainDemo
~~~

Stdout on successful run:

~~~text
reply: HELLO
reply: NIO2
handled: 2
~~~

### 7.1. Why the demo does not lose state

1. `server.accept(...)` registers an accept, and the callback receives `peer`. On the first connection, the callback re-arms accept to continue accepting the second connection.
2. `new Session(peer, ...)` creates a **separate 4-byte header** for each peer. No global buffer is used; the Session is referenced by callbacks throughout the pipeline.
3. `readHeader()` calls `peer.read(header, null, handler)`. If only 1–3 bytes are read, the callback calls `readHeader()` again on **the same header**, with position not reset. Only when all 4 bytes are present does it `flip`, decode the length, and validate `1..1024`.
4. `readPayload()` allocates a buffer of the exact validated length. If only part of the payload has arrived, the callback continues reading into **the same payload**. When all bytes are present, it `flip`s and copies the bytes into application data.
5. `PROCESS` builds the uppercase reply once and then packs the response consisting of the length prefix and bytes. The response ByteBuffer is `flip`ped **once** before sending.
6. `writeResponse()` writes the remaining bytes. If the write completes only partially, the callback continues writing from the current `response.position()`, without closing the peer while `hasRemaining()` is true.
7. After the entire response has been handed to the channel, the Session closes the peer and increments the counter. `CompletableFuture all` is completed when both sessions finish. The main thread waits on `all.get(...)` so the demo exits deterministically.

**Important:** `CompletableFuture` in the code above is used to **coordinate when the entire demo finishes**, not to replace the read/write `CompletionHandler`s. The client code uses blocking streams for testing, while the server-side processing flow uses asynchronous channels exclusively.

### 7.2. Why not rely on callback/thread ordering?

Two Sessions may be processed on different worker threads, and callbacks may switch threads between steps. In the program, each callback **retains ownership** of the Session's state and only starts a dependent operation after the previous operation completes.

Printing replies in the order `HELLO` then `NIO2` happens because **the test client sends the two requests sequentially**, not because NIO.2 guarantees processing order across connections. If two clients run concurrently, callback order depends on scheduling, I/O, and load conditions; use a separate request ID/state to match responses.

### 7.3. Limitations of the demo

- Accepts only **two connections**, each with **one request**, then closes; it is not a long-running server.
- Each request must have a length in `1..1024`; zero-length is rejected due to the **demo's rule**, not a mandatory NIO.2 limitation.
- Uses ASCII and uppercasing with `Locale.ROOT`; does not support Unicode normalization, TLS, authentication, or heavy business logic.
- The example only has `CompletableFuture.get(5s)` in main and a blocking timeout on the client; it does not configure **server-side** read/write timeouts. In production, a deadline/idle timeout on the session is needed, closing it when expired.
- Callbacks create new handler objects on every re-arm. This is simple for learning; under high load, consider reducing allocations, using an optimized state machine, or an appropriate framework.
- On an unexpected error in a callback, `fail` closes the peer and fails the Future. Production needs detailed logging/metrics conventions, protection against double-close/double-complete, and guaranteed single-time permit release.

The demo is designed to **verify the correct processing order**, not as a throughput benchmark or a production server recipe.

## 8. Partial read: why one callback does not necessarily complete a frame

When requesting to read a 4-byte header, `AsynchronousSocketChannel.read` only promises the result **of that single read call**. It may complete with 1, 2, or 3 bytes; at that point `header.position` has already been incremented automatically, and you continue reading in the callback. **Do not allocate a new `ByteBuffer.allocate(4)` on each completion**, as that discards the bytes already received.

~~~text
Header buffer:
[ 00 00 00 05 ]
     ^
     header.position after 2 bytes = 2

Next read uses THAT EXACT buffer:
peer.read(header, attachment, handler)

When header.remaining()==0:
header.flip(); int length=header.getInt();
~~~

In the EOF case, `read` returns `-1`. In the demo, EOF while reading the header or payload is treated as an error for simplicity; in a multi-request protocol, EOF right at the **boundary before a new request** can be accepted as a normal session end, whereas EOF mid-header/mid-payload is a **truncated frame**.

**`read()==0` is not EOF.** With asynchronous I/O, it can occur because the buffer has no remaining space (`remaining()==0`) or completes without transferring bytes; in a pipeline that bounds ByteBuffers properly, only call read when the buffer still has `hasRemaining()`. If it completes with `0` while remaining is still non-zero, preserve state and apply a retry/deadline policy; do not turn `0` into an empty frame or an EOF.

## 9. Partial write: do not close the socket too early

A common mistake:

~~~java
// WRONG: asynchronous write has only BEEN INITIATED.
peer.write(response, null, handler);
peer.close(); // May close before the write completes.
~~~

Another mistake:

~~~java
// WRONG: flipping the buffer again after each partial write,
// which may re-send the prefix or already-sent payload.
peer.write(response, null, handler);
response.flip();
~~~

The right way:

1. Put `response` into read mode **once** after `putInt(length)` and `put(payload)`.
2. Call `write(response, attachment, handler)`.
3. In `completed(n, attachment)`, check `response.hasRemaining()`. If true, re-arm write with **the same buffer**; if false, consider the frame send operation complete at the channel level.
4. Only after that should you close the socket or start a step that must wait for the response to be fully sent, depending on the protocol.

Completion of `write` **does not confirm that the receiver has processed the business logic**. It only confirms that the data has been written by the channel per the API contract. To know the client received/processed it, the protocol needs an ACK or application-level response.

If multiple messages are produced on one connection, an **outbound queue** or a single Future/completion chain is needed so multiple overlapping writes are not initiated. `WritePendingException` and interleaved bytes can prevent the client from decoding the framing.

## 10. Using attachment to manage Phase, request ID, and deadline

A production Session typically has explicit state:

~~~java
// Structural illustration, not a standalone runnable program.
enum Phase {
    READ_HEADER, READ_PAYLOAD, PROCESS, WRITE_RESPONSE, DONE, FAILED
}

final class SessionState {
    final AsynchronousSocketChannel peer;
    final ByteBuffer header = ByteBuffer.allocate(4);
    ByteBuffer payload;
    ByteBuffer response;
    Phase phase = Phase.READ_HEADER;
    long deadlineNanos;
    long requestId;

    SessionState(AsynchronousSocketChannel peer) {
        this.peer = peer;
    }
}
~~~

The snippet above requires importing `java.nio.ByteBuffer` and `java.nio.channels.AsynchronousSocketChannel`. It highlights that the fields persist for the **duration of the session**, rather than disappearing after `accept` returns.

You can pass `session` directly as the attachment:

~~~java
// Pseudocode: session/handler already declared in the application.
session.peer.read(session.header, session, headerHandler);
~~~

When the callback is invoked, `attachment` is still a reference to **the same Session**. Inside the callback, you can read `session.phase` and check if the message is in an unexpected phase; if a mismatch is detected, report an error/close to prevent races.

### 10.1. Callback threads are not transaction locks

Do not assume that because operations are “chained”, all shared data is automatically safe. If a management thread can close a Session while a callback is writing a reply, a **lifecycle guard** is needed, such as `AtomicBoolean closed` or coordinating state changes through a single executor/actor.

An idempotent cleanup pattern:

~~~java
// Illustration: placed inside Session, closed variable initialized once.
private final AtomicBoolean closed = new AtomicBoolean();

void closeOnce() {
    if (closed.compareAndSet(false, true)) {
        try {
            peer.close();
        } catch (IOException closeError) {
            // Log or add as suppressed to the original error.
        }
        // Release the connection permit exactly once.
    }
}
~~~

This snippet requires importing `java.util.concurrent.atomic.AtomicBoolean` and `java.io.IOException`. Call `closeOnce()` in both success and failure paths, and do not release the permit in both `closeOnce` and another callback. With an idempotent handler, avoid double-completing a Future or double-replying when a timeout and a network failure race.

### 10.2. Signs of “losing state”

- The first callback receives 2 header bytes; the next callback allocates a new header and drops the first 2 bytes.
- After receiving 50 payload bytes, retrying read with a new buffer at `position=0` without preserving the old offset.
- Writing 7/100 bytes and then calling `clear()` on response; the next write re-sends from byte 0.. instead of byte 7...
- Client A's callback writes into a static requestBuffer, and Client B modifies the buffer before A processes it.
- Completing the response Future/callback **immediately** after calling `write(...)`, while the write is still pending.
- A failure path closes the socket but forgets to remove the session from the map or return the semaphore permit.
- Enqueueing request B while request A has not finished writing, with multiple writers sending concurrently and interleaving the two responses.

Each of these bugs can be avoided with **per-connection state + a single operation owner + clearly defined phase transition points**.

## 11. Futures, CompletionHandler, and CompletableFuture: choosing a chaining mechanism

NIO.2 can return a `Future` for an operation:

~~~java
Future<Integer> future = peer.read(buffer);
// Elsewhere: future.get() will wait for the I/O to complete.
~~~

This is **illustrative code**. If you call `future.get()` directly inside an I/O completion worker, you can **block** a worker needed to serve other completions. Only use blocking Future calls when the calling thread is genuinely allowed to wait (for example, the main thread of a demo program), or attach a continuation on an appropriate executor.

With `CompletionHandler`:

~~~java
peer.read(buffer, attachment, handler);
// Do not wait here; handler.completed will continue the chain.
~~~

`CompletableFuture`/`CompletionStage` has `thenCompose` and `thenApply` to express dependencies, but understand that **a single read is not guaranteed to receive a full frame**. Do not simply wrap one `read` and call `thenApply(parseFrame)`, because the parser might receive 1/4 of a header. You must write asynchronous **readFully/writeFully** helpers to complete **the full byte count**, and only then compose the processing step.

When using `thenApply`, business logic runs on the stage-completing thread according to CompletionStage semantics; for long CPU/DB work, use `thenApplyAsync` on a managed executor or an appropriate offloading mechanism. Do not perform blocking JDBC or heavy CPU calculations inside a read callback if it stalls the I/O worker pool.

## 12. Error handling: accept, read, process, and write all need a failed branch

### 12.1. Errors in each phase

| Phase | Error/condition | How to handle |
| --- | --- | --- |
| Accept | Listener closed/shutdown, OS reports error, out of capacity | Do not leak client sockets; stop/retry per policy |
| Read header | EOF mid-4 bytes, I/O exception, timeout | Report truncated header; close session |
| Validate | Negative/oversized length, wrong message type/version | Reject before allocation; close or send error per protocol |
| Read payload | EOF mid-N bytes, reset, timeout | Do not treat incomplete payload as a valid frame |
| Process | Parser/logic throws exception, malicious data | Log error with context, do not crash the listener |
| Write | Partial write, write timeout, remote reset | Keep unsent part or terminate session per policy |
| Cleanup | Close/permit-release error | Preserve root cause, idempotent cleanup |

In Java, the `failed(Throwable error, A attachment)` callback reports errors **of the I/O operation**. However, logic you write inside `completed` can also throw exceptions, and the runtime does not automatically “convert” all such programming errors into `failed`. The demo puts a `try/catch` inside `completed` and calls `fail` so cleanup is never missed.

A `SocketTimeoutException` from traditional blocking `Socket` is not always how NIO.2 reports timeouts. In asynchronous read/write with a timeout, the error may be `InterruptedByTimeoutException`. Do not use the wrong exception class to infer the phase.

### 12.2. Timeouts and indeterminate I/O state

`AsynchronousSocketChannel` has read/write overloads with timeout parameters:

~~~java
// Java NIO.2, illustrative snippet with compatible session and handler.
peer.read(buffer, 3, TimeUnit.SECONDS, session, readHandler);
peer.write(reply, 3, TimeUnit.SECONDS, session, writeHandler);
~~~

In the `failed` callback, handle timeouts alongside I/O errors. When an asynchronous operation times out, **do not assume you can safely reuse the same ByteBuffer and socket**: an operation may have transferred some bytes or left the state unsuitable for recovery. For protocols requiring strict correctness, it is usually best to **close the session** and reconnect per application policy.

A single read/write timeout is not automatically a total deadline for **the entire request**. A peer could send a few bytes before each timeout and drag it out indefinitely. Store `deadlineNanos` using `System.nanoTime()` and check the remaining time between phases; use a scheduled timeout to close the connection if the budget is exceeded.

### 12.3. Complete a promise only once

If a caller awaits a `CompletableFuture<Response>`, there should be a single place deciding the DONE/FAILED state. Closing the session, recording logs/metrics, and calling `complete`/`completeExceptionally` must have anti-race rules; two callbacks or a deadline timer might try to finish at the same time.

`CompletableFuture.complete(...)` returns `false` if it was already completed earlier; this can be used to observe behavior, but releasing the socket/permit should still live in a `closeOnce()` guard. Do not rely on `complete` to automatically close network resources.

## 13. Running with many clients: concurrency and resource limits

Asynchronous channels do not mean “no threads needed”. The JDK processes I/O completions through a provider and thread pool (`AsynchronousChannelGroup`), which you can specify or leave as default. This model avoids keeping a blocked platform thread per client in the same way as blocking thread-per-connection, **but it still consumes**:

- File descriptors/sockets and kernel buffers.
- Heap for `Session`, header/payload/response buffers.
- Workers executing callbacks, CPU for parsing/serialization and business logic.
- Connections to databases/downstream services.
- Application task queues and pending requests.

### 13.1. Admission control before starting a Session

Example setting a limit of 100 active connections (just an **illustrative value**):

~~~java
// Illustration in the accept callback, semaphore owned by the server.
Semaphore permits = new Semaphore(100);

// After accepting peer:
if (!permits.tryAcquire()) {
    peer.close(); // Overloaded: close immediately, do not create session.
} else {
    Session session = new Session(peer);
    // When Session ends (success/error):
    // closeOnce() must release the permit exactly once.
    session.readHeader();
}
~~~

This illustrative code is not standalone and does not include the real `Session` class. `Semaphore` protects the number of sessions consuming resources, not merely the number of currently running callbacks. Do not acquire a permit in this branch and then release it in both `failed` and another `finally` without a guard.

### 13.2. Outbound backpressure

If a client reads slowly, writes will complete slowly or only partially. If the application keeps generating new responses and queueing them unboundedly, memory balloons. You need an outbound queue bounded by **byte count**, preserving the offset of each `ByteBuffer`, and allowing only one pending write per direction. When the queue exceeds its threshold, slow down request reading, reject new requests, or close the session per policy.

Do not try to parallelize multiple writes on the same connection to “drain the queue”: wire format order must be preserved; if the protocol requires multiplexing, use a single serializer and request IDs rather than letting threads write arbitrarily.

### 13.3. Callbacks must not do heavy work

A completion handler should do a small amount of work: check the result, update state, schedule the next I/O. For requests requiring long computation, blocking DB operations, or remote service calls, offload to a separate executor and chain the continuation back to the Session. If heavy work runs directly on a completion thread, other connections can stall even though I/O is async.

However, **offloading does not mean concurrently mutating the same ByteBuffer**. A business-logic executor should build the response from a **complete snapshot of the request data**, and only one continuation should be allowed to update the response buffer/phase when processing finishes.

## 14. Ordered shutdown

A real server needs a shutdown path:

1. Mark **not accepting new connections** (thread-safe lifecycle flag).
2. Close `AsynchronousServerSocketChannel` to cancel any pending accept; a `failed` callback during shutdown is expected, do not retry infinitely.
3. Decide whether to drain active Sessions within a deadline or close immediately per SLA.
4. Close expired peer sockets, causing pending I/Os to fail or be cancelled per API; idempotent session cleanup.
5. If using a self-managed `AsynchronousChannelGroup`, shut down the group following `shutdown()`/`awaitTermination(...)` and then `shutdownNow()` if needed; do not close the group while critical work is still unprocessed.
6. Clean up business executors, counters, logging, pending promises, and queues. If the application handles idempotent operations, persist information for retry/reconciliation.

Do not let `accept.failed` unconditionally call `acceptNext` whenever the listener closes; otherwise it can create a continuous error loop. Do not assume a `close()` call means all unsent responses have been successfully flushed.

## 15. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `read` right after `accept(...)` on a variable with no peer yet | Do not know which socket was accepted yet | Start reading inside `accept.completed(peer, ...)` |
| Calling accept only once | Server stops accepting new clients after the first connection | Re-arm accept in the completion callback |
| Calling accept a second time while the previous one is pending | `AcceptPendingException` | Only one pending accept on the listener |
| Decoding when a read only has 1/4 of the header | `BufferUnderflowException` or corrupt frame | Re-read into the same header until 4 bytes |
| Recreating header/payload on every callback | Loss of already-received bytes/offset | Use Session fields and preserve `ByteBuffer.position` |
| Calling `flip()` on response after a partial write | Re-sending prefix or payload | Flip once, continue writing from current remaining |
| Closing peer immediately after calling `write` | Response may not have finished sending | Close in write completed when no remaining |
| Calling two reads/writes in the same direction while one is pending | `ReadPendingException`/`WritePendingException` | Serialize I/Os by direction and phase |
| Using a static ByteBuffer variable for all clients | Races and interleaved bytes across sessions | One Session per connection |
| Calling blocking `Future.get()` on a completion thread | Blocks worker from serving other I/Os | Use callbacks/continuations, offload work appropriately |
| Forgetting to catch exceptions in `completed` | Cleanup is not executed | try/catch and centralized fail handling |
| Calling process on EOF mid-payload | Processing an incomplete frame | Distinguish EOF at frame boundary vs. truncated frame |
| Not validating length before allocation | DoS or memory errors | Max frame length, rate/size limits |
| Timer and callback both closing/releasing | Double cleanup, lost permit | Atomic `closeOnce`/lifecycle state |
| Re-arming accept infinitely during shutdown | Infinite error/retry loop | Check `running`, do not retry when listener is closed |
| Thinking asynchronous means “no limits needed” | Exhausted sockets, heap, DB connections | Admission control, queue/buffer limits |
| Calling the next write in callback while creating a new response | Corrupts content being sent | Store response buffer once, use remaining |
| Confusing completion order between client A and B | Mismatched response/request | Separate Session, request ID, do not rely on thread order |

## 16. Self-check exercises

### Exercise A: Header read as 1+2+1

Accept succeeds, 4-byte header buffer. Three read callbacks return 1, 2, 1 respectively. When do we decode the length?

**Answer:** after the third callback, when `header.hasRemaining()==false`. Before that, keep `header.position` unchanged and continue calling read on the same buffer. Only after all four bytes are present do we `flip()` and `getInt()`.

### Exercise B: 100-byte response written as 40+0+60

First write callback returns 40; next returns 0; last returns 60. Can we close the connection after the first one?

**Answer:** no. After 40 bytes, `response.remaining()==60`, so it is not done. `0` is neither closed nor full success; keep the buffer and retry per completion/deadline. Only when `remaining()==0` is the wire response complete at the channel level.

### Exercise C: Two clients arrive together

Client A is accepted and waiting for payload; client B starts connecting. Why can the server accept B before A finishes processing?

**Answer:** after accepting A completes, the server re-arms a new accept before running A's handler. Sessions are independent: B has its own Session and buffers. There is no need to wait for A's request to finish to accept B, as long as admission control still has permits.

### Exercise D: Client closes mid-payload

Decoded length is 200, but the receiver only gets 50 bytes and then the read callback returns -1. Can we process the 50 bytes?

**Answer:** no. The 200-byte payload is incomplete: this is a truncated frame. Close the session or report a protocol error; do not treat EOF as a “valid end” when bytes are still missing.

### Exercise E: Running heavy CPU parsing inside the completion callback

The server has many clients; the handler runs a 2-second CPU-intensive algorithm directly inside `completed`. What is the danger?

**Answer:** the worker serving completions is occupied for 2 seconds, which can delay other sessions. Offload heavy tasks to a concurrency-bounded executor, keep a request snapshot, and coordinate a continuation to update the right Session.

### Exercise F: Timeout and write race

The timeout timer closes the peer right as the write callback finishes. Both branches call `releasePermit()`. How do we prevent releasing twice?

**Answer:** use an idempotent lifecycle `closeOnce()`/`AtomicBoolean.compareAndSet`, centralize cleanup in one place, and allow only the winning owner to transition to DONE/FAILED. Closing the socket/cancelling I/O must be handled as part of the state machine, not by scattering arbitrary cleanup calls.

### Exercise G: One accept still pending

An application calls two `server.accept(...)` in a row without waiting for completion. What is the result?

**Answer:** with `AsynchronousServerSocketChannel`, only one accept can be pending at a time; the second call may throw `AcceptPendingException`. Only re-arm from the callback when the previous accept has completed.

### Exercise H: Future.get inside a callback

A developer calls `peer.read(buffer).get()` from a completion handler running on a small worker pool. Why shouldn't they?

**Answer:** `get()` is a blocking wait that can hold up a worker needed for other completions, increasing the risk of stalls or deadlocks depending on the thread pool design. Chain with callbacks or a non-blocking `CompletionStage` model; only wait on a thread that is allowed to block.

## 17. Asynchronous pipeline design checklist

- [ ] Does the server have **exactly one pending accept** and re-arm when accept completes?
- [ ] Does each accepted connection have its own **Session state**, with no unsynchronized shared ByteBuffers?
- [ ] Does the state explicitly track phases for reading header, reading payload, processing, writing response, and cleanup?
- [ ] Do partial reads preserve the ByteBuffer and `position` until all bytes are read?
- [ ] Is frame length validated before allocating the payload buffer?
- [ ] Is `read==-1` mid-frame handled as truncated, rather than treated as a complete message?
- [ ] Do partial writes preserve the response buffer and only close/transition phase when `hasRemaining()` is false?
- [ ] Are there never two pending reads or two pending writes in the same direction on a connection?
- [ ] Are completion handlers short, without calling blocking `Future.get()` or heavy CPU/DB work directly in the callback?
- [ ] Do callbacks, timers, and other threads share state via appropriate synchronization?
- [ ] Are there `failed`/try-catch handlers for every phase and idempotent cleanup on error?
- [ ] Are there deadlines/idle timeouts and limits on connection count, frame size, and outbound buffers?
- [ ] Does shutdown close the listener, stop accepting, drain/close sessions, and shut down groups/executors in the right order?
- [ ] Have scenarios like 1+3 header, partial payload, partial write, EOF mid-frame, malformed length, slow client, and close mid-callback been tested?

**Conclusion:** NIO.2 lets you initiate `accept`, `read`, and `write` without blocking the calling thread, but **business order does not appear by itself**. To chain correctly, transition steps **only at completion**, keep a **Session** and **ByteBuffers** across callbacks, read/write until all bytes are transferred, and close the session exactly once. When you add framing, timeouts, resource limits, error paths, and controlled shutdown, an asynchronous TCP pipeline becomes reliable under concurrent clients.
