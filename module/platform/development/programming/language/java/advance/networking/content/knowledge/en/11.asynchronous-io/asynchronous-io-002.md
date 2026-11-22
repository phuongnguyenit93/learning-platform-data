# AsynchronousServerSocketChannel and AsynchronousSocketChannel in Java NIO.2

**Asynchronous I/O** allows an application to **initiate an accept, connect, read, or write operation** and receive the result later, instead of forcing the calling thread to wait until the I/O task completes. In Java 17, the two key TCP networking APIs at this layer are **java.nio.channels.AsynchronousServerSocketChannel** (a listener accepting connections) and **java.nio.channels.AsynchronousSocketChannel** (a readable/writable TCP connection). They belong to **NIO.2**, introduced in Java 7.

The key point is that **asynchronous does not automatically mean faster or threadless**, and **it is not synonymous with non-blocking SocketChannel + Selector**. Asynchronous channels use **Future** or **CompletionHandler** to report results; the provider/JVM and the operating system manage completion mechanisms, callback dispatching, and resources behind the scenes. The I/O initiation call usually returns immediately, but if you subsequently call **Future.get()** right on the same thread, that thread still blocks waiting for the result.

This Knowledge article belongs to the **Asynchronous I/O** section. After this lesson, you should be able to: choose the right roles for server/client asynchronous channels, understand **accept/connect/read/write** with Future and callbacks, use ByteBuffer and handle partial I/O, manage at most one pending operation per direction, design timeouts/cancellation/group lifecycle, interpret exceptions properly, and write a runnable Java 17 TCP echo demo.

## 1. Distinguishing Three Common TCP I/O Models

| Model | Typical API | How the application receives results | Notes |
|---|---|---|---|
| Blocking I/O | **ServerSocket**, **Socket** | **accept/read/write** calls return after completion or throw an error | Easy to write sequentially; calling thread may block |
| Non-blocking readiness I/O | **ServerSocketChannel**, **SocketChannel**, **Selector** | **select()** reports readiness; application actively calls **accept/read/write** and manages **OP_CONNECT/OP_READ/OP_WRITE** | May return 0/partial I/O; application drives the event loop |
| Asynchronous completion I/O | **AsynchronousServerSocketChannel**, **AsynchronousSocketChannel** | Receives **Future** or **CompletionHandler.completed/failed** callback when the operation finishes | Results arrive asynchronously; must manage outstanding operations, ByteBuffer, and lifecycle |

**NIO.2 asynchronous socket channels do not register with a Selector** and do not require **configureBlocking(false)**. Do not copy a SocketChannel **OP_ACCEPT/OP_CONNECT** loop verbatim onto AsynchronousSocketChannel. With the async API, initiate an operation and receive its completion; if using callbacks, the callback should only do brief work and initiate the next I/O step.

Both asynchronous channels operate on a **TCP byte stream** and do not automatically add message framing, business request ordering, TLS, or retry/idempotency logic. Even when a completion callback reports that a **write** has completed, the peer **has not necessarily** processed the message at the application layer.

### Lifecycle Diagram

~~~text
                    Server (listener)
AsynchronousServerSocketChannel.open()
              |
           bind(...)
              |
           accept() -------------------------------------+
              |                                         |
        Future<AsynchronousSocketChannel>                |
              |                                         |
         accept completes                               |
              |                                         |
         accepted peer  <----- TCP connection -----  client
              |                                  AsynchronousSocketChannel.open()
              |                                            |
              |                                         connect(...)
              |                                            |
         read(ByteBuffer)                    Future<Void> / CompletionHandler
              |                                            |
         write(ByteBuffer)                               read/write
              |                                            |
         close accepted peer                           close client
              |
         close listener
~~~

**Listener** and **accepted peer** are two different objects. Closing an accepted channel ends **one connection**, not the listener. Closing the listener stops accepting new connections; already created accepted channels must be managed and closed separately.

## 2. AsynchronousServerSocketChannel: Listener and Asynchronous Accept

The listener is created and then bound to an address and port:

~~~java
AsynchronousServerSocketChannel listener =
        AsynchronousServerSocketChannel.open();
listener.bind(new InetSocketAddress("127.0.0.1", 0));
~~~

This is an **illustrative API snippet**, not a standalone program, and the listener must be closed at the end. Port **0** asks the OS to choose an ephemeral port; read the actual address via **listener.getLocalAddress()**. A newly opened listener is **not yet bound**; calling **accept** too early throws **NotYetBoundException**.

Two important overloads:

~~~java
Future<AsynchronousSocketChannel> next = listener.accept();
listener.accept(attachment, completionHandler);
~~~

- **accept()** returns **Future<AsynchronousSocketChannel>**. Calling **Future.get()** upon success returns the channel representing the newly accepted connection, not the listener itself.
- **accept(A attachment, CompletionHandler<AsynchronousSocketChannel, ? super A> handler)** initiates the operation and then calls **completed(acceptedChannel, attachment)** or **failed(throwable, attachment)**.
- **At most one accept can be pending on the same listener.** Calling another accept before the previous operation completes causes Java to throw **AcceptPendingException**. This does **not** mean a server can serve only one client; each accepted channel is handled separately while the listener continues accepting.
- **bind(local, backlog)** takes a suggested backlog parameter; the listening queue limit and specific enforcement depend on the OS/implementation, **not** a limit on the number of accepted clients.
- The listener and accepted channels can belong to a shared **AsynchronousChannelGroup**, depending on the configured group.

### Why Is Accept Usually Re-Armed in the Callback?

A continuously running listener needs to **initiate the next accept after the previous one has completed**, rather than looping accept calls while one is still pending:

~~~java
listener.accept(null,
        new CompletionHandler<AsynchronousSocketChannel, Void>() {
            @Override
            public void completed(
                    AsynchronousSocketChannel peer, Void ignored) {
                listener.accept(null, this); // Re-arm for the next client.
                handle(peer);                 // Handle the newly accepted connection.
            }

            @Override
            public void failed(Throwable error, Void ignored) {
                report(error);                // Apply error/close policy.
            }
        });
~~~

**This is only an illustrative snippet**: **handle(peer)** and **report(error)** are application-defined methods, not a standalone runnable file. In a real server, you must check whether the listener is closing, wrap the re-arm operation with synchronous error handling, limit concurrent connections, and ensure every accepted peer has an owner responsible for closing it. Do not re-arm when the server is shutting down.

Do not confuse the "one pending accept" rule with "one running callback." A completed accept operation can hand the peer to the callback; at that point you can start the next accept, while the previous connection is handled using read/write operations on the accepted channel.

## 3. AsynchronousSocketChannel: TCP Connection and ByteBuffer Exchange

The client creates an unconnected channel:

~~~java
AsynchronousSocketChannel client = AsynchronousSocketChannel.open();
Future<Void> connecting = client.connect(remoteAddress);
connecting.get(); // Blocks the current thread until completion.
~~~

The snippet above is illustrative, not a standalone program; **remoteAddress** must be specified. A newly opened channel is **open but not yet connected**. **connect(SocketAddress)** returns **Future<Void>**; on successful completion, **get() returns null**, not boolean true or a Socket. If connect fails, Future.get throws **ExecutionException** whose cause contains the I/O error. The corresponding callback API:

~~~java
client.connect(remoteAddress, attachment,
        new CompletionHandler<Void, MyState>() {
            @Override
            public void completed(Void ignored, MyState state) {
                // Connection succeeded; can start read/write.
            }

            @Override
            public void failed(Throwable error, MyState state) {
                // Log error and clean up channel.
            }
        });
~~~

This is also an illustration with a custom **MyState**. **AsynchronousSocketChannel does not use finishConnect()**; that is a **SocketChannel** API in the Selector/non-blocking model. Nor is there an **isConnectionPending()** like SocketChannel. According to the AsynchronousSocketChannel documentation, you can check the remote address with **getRemoteAddress()**: it returns **null** when not yet connected; however, application design should explicitly track **state and completion**, rather than just polling the address.

**Only one connect operation can be performed for a channel.** Calling connect again while a previous operation is still pending can throw **ConnectionPendingException**; calling connect when already connected throws **AlreadyConnectedException**. If connect fails, the channel is closed per the API contract. To retry, create a **new** channel and respect deadlines/backoff.

### Asynchronous Read and Write

~~~java
Future<Integer> reading = client.read(dst);
Future<Integer> writing = client.write(src);
~~~

- **read(ByteBuffer)** returns **Future<Integer>**, where a successful get yields the number of bytes read or **-1** on EOF.
- **write(ByteBuffer)** returns **Future<Integer>**, where a successful get yields the number of bytes written from the ByteBuffer to the channel.
- You can use **CompletionHandler<Integer, AttachmentType>** instead of Future to receive the byte count and attachment.
- For **read/write**, completing one operation does not mean reading/writing an entire **message**. If the ByteBuffer still has bytes to send or not enough bytes have been received according to framing, you must initiate the next operation **after the previous operation completes**.
- **Read and write are independent:** you can have one pending read **concurrently** with one pending write on the same AsynchronousSocketChannel (full-duplex), but **you must not have two pending reads or two pending writes at the same time**. Java will throw **ReadPendingException** or **WritePendingException**.

### No Auto-Framing

TCP is a **byte stream**. If an application writes two messages, the receiver must not assume there will be exactly two read callbacks. To know where a message ends, you need **a length prefix, delimiter, or EOF rule**, along with size limits. A callback only tells you that one I/O batch completed with a specific byte count; it does not split messages automatically.

## 4. Two Completion Styles: Future and CompletionHandler

| Question | Future API | CompletionHandler API |
|---|---|---|
| Initiation | **Future<T> op = channel.read(buffer)** | **channel.read(buffer, attachment, handler)** |
| Receiving result | **op.get()** or **op.get(timeout, unit)** | **completed(result, attachment)** |
| Receiving error | **get()** may throw **ExecutionException** | **failed(Throwable, attachment)** |
| Blocks caller? | Initiation call need not block long; **get() will block if not finished** | Handler is invoked on completion; caller does not need to wait if callbacks are structured |
| State management | State held by caller/future coordinator | **attachment** carries the operation's state |
| Major pitfalls | Calling get inside an event loop/callback, accidentally blocking | Deeply nested callbacks, callback throwing exceptions, improperly shared buffers, overly heavy processing |

### Future Does Not Guarantee the Whole Program Is Asynchronous

~~~java
Future<Integer> f = channel.read(dst);
int n = f.get();
~~~

At the time **read** is called, the operation has been started asynchronously. Immediately afterward, however, **get** blocks the current thread until a result is available. This is a useful choice for examples and simple sequential tasks, but **if you always call get immediately on a single thread/event loop**, the application cannot take advantage of multiple concurrently pending I/O operations. You can initiate valid operations on multiple channels first and coordinate Futures, or use CompletionHandler/CompletableFuture so you do not have to block the coordinating thread.

### CompletionHandler Has Two Paths, Both Must Be Handled

~~~java
channel.read(dst, myAttachment,
        new CompletionHandler<Integer, MyState>() {
            @Override
            public void completed(Integer bytes, MyState state) {
                // Check bytes, handle partial read and EOF.
            }

            @Override
            public void failed(Throwable error, MyState state) {
                // Notify caller, release channel/buffer/state.
            }
        });
~~~

The snippet above has a custom **MyState** and is not a standalone runnable file. **Attachment** is data associated with *an operation* (connection context, buffer, request id...), not the I/O result. Do not write arbitrary data to a shared attachment without synchronization; completion callbacks may run on a **thread belonging to the group**, not the thread that initiated the operation.

In callbacks, avoid running long DB queries, heavy JSON processing, or waiting on **Future.get()** from an operation that depends on the same pool. That risks stalling completion threads and causing starvation/deadlock. If CPU-bound work or blocking DB work is needed, offload heavy work to another bounded executor and design backpressure.

## 5. Complete Java 17 Example: TCP Echo Using Future

This example opens an **asynchronous server** and an **asynchronous client** on loopback with an OS-assigned port, requiring no external services. The minimal protocol specifies an exact **4-byte PING** request and an exact **8-byte ACK:PING** response; because the lengths are known in advance, the **readExactly** helper can read until enough bytes arrive without waiting for EOF.

The listener, client, and accepted channel are all closed using **try-with-resources**. **Future.get(timeout)** applies a timeout while waiting; if an exception occurs, try-with-resources closes the channels. This is a **Future-based** demo, as main can still block when calling get; the learning goal is understanding completion and partial I/O, not benchmarking throughput.

File **AsyncFutureEchoDemo.java**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class AsyncFutureEchoDemo {
    private static final long WAIT_SECONDS = 3L;

    private static void writeAll(
            AsynchronousSocketChannel channel, ByteBuffer data)
            throws Exception {
        while (data.hasRemaining()) {
            int written = channel.write(data)
                    .get(WAIT_SECONDS, TimeUnit.SECONDS);
            if (written < 0) {
                throw new IOException("Write terminated unexpectedly");
            }
        }
    }

    private static void readExactly(
            AsynchronousSocketChannel channel, ByteBuffer dst)
            throws Exception {
        while (dst.hasRemaining()) {
            int n = channel.read(dst)
                    .get(WAIT_SECONDS, TimeUnit.SECONDS);
            if (n == -1) {
                throw new EOFException("EOF before expected bytes");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open()
                             .bind(new InetSocketAddress(loopback, 0));
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            Future<AsynchronousSocketChannel> accepting =
                    listener.accept();
            Future<Void> connecting =
                    client.connect(listener.getLocalAddress());

            // Success: Future<Void>.get() returns null.
            connecting.get(WAIT_SECONDS, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel peer =
                         accepting.get(WAIT_SECONDS, TimeUnit.SECONDS)) {

                writeAll(client,
                        StandardCharsets.UTF_8.encode("PING"));

                ByteBuffer serverInput = ByteBuffer.allocate(4);
                readExactly(peer, serverInput);
                serverInput.flip();
                String request = StandardCharsets.UTF_8
                        .decode(serverInput).toString();

                writeAll(peer, StandardCharsets.UTF_8
                        .encode("ACK:" + request));

                ByteBuffer clientInput = ByteBuffer.allocate(8);
                readExactly(client, clientInput);
                clientInput.flip();
                String response = StandardCharsets.UTF_8
                        .decode(clientInput).toString();

                System.out.println("Server received: " + request);
                System.out.println("Client received: " + response);
            }
        }
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac -encoding UTF-8 AsyncFutureEchoDemo.java
java AsyncFutureEchoDemo
~~~

Stdout on successful run:

~~~text
Server received: PING
Client received: ACK:PING
~~~

### Exact Breakdown

1. **AsynchronousServerSocketChannel.open().bind(...,0)** creates a listener on loopback and an ephemeral port. **accept()** starts accepting a connection and returns a Future without waiting.
2. **AsynchronousSocketChannel.open()** creates an unconnected client. **connect(listener.getLocalAddress())** starts connecting and returns **Future<Void>**.
3. **connecting.get(3,SECONDS)** waits for the connection to succeed; if refused/errored, get throws an exception and the program does not enter read/write.
4. **accepting.get(3,SECONDS)** returns the accepted **AsynchronousSocketChannel peer**. That is **a different channel from the listener**, with its own close responsibility.
5. The client sends the exact 4 bytes **PING**. The writeAll helper continues calling write **sequentially after the previous Future completes** if the ByteBuffer still has remaining bytes.
6. The server's readExactly reads the exact 4 bytes across one or more read operations; it does **not** assume one read is guaranteed to be enough.
7. The server sends **ACK:PING**, and the client reads the exact 8 bytes. Both ByteBuffers are **flipped** before UTF-8 decoding.
8. Both stdout lines are printed in main after all required operations complete; they do not depend on dynamic ports or callback ordering, so the output is deterministic when the demo succeeds.

**Intentional scope:** the demo only has a single fixed-size request/response and does not handle high throughput. Real data requires framing, maximum length, application deadlines, structured outstanding operations, security, distinguishing EOF from partial messages, and resources for multiple clients. Each **Future.get(3s)** sets the *caller's* wait limit; the entire transaction can take longer than 3 seconds due to multiple sequential gets. In production, compute an **overall deadline** and close unfinished channels when the deadline expires.

## 6. Complete Java 17 Example: Accept, Connect, and Read with CompletionHandler

The second example uses callbacks to represent events, instead of obtaining accept/connect Futures and calling get. The listener initiates **accept(null, handler)**; the client initiates **connect(..., null, handler)**; the server initiates read callbacks multiple times if needed until four bytes arrive. **CompletableFuture** is only used so main can wait for the final result and print deterministic stdout; the accept/connect/read operations themselves are all callback-based.

File **AsyncHandlerDemo.java**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class AsyncHandlerDemo {
    private static void closeQuietly(AsynchronousSocketChannel ch) {
        try {
            ch.close();
        } catch (IOException ignored) {
            // Cleanup only after reporting the result.
        }
    }

    private static void readFour(
            AsynchronousSocketChannel peer,
            ByteBuffer buffer,
            CompletableFuture<String> received) {
        try {
            peer.read(buffer, buffer,
                    new CompletionHandler<Integer, ByteBuffer>() {
                @Override
                public void completed(Integer n, ByteBuffer dst) {
                    if (n == -1) {
                        received.completeExceptionally(
                                new EOFException("EOF before 4 bytes"));
                        closeQuietly(peer);
                        return;
                    }

                    if (dst.hasRemaining()) {
                        // The previous read completed; only now read next.
                        readFour(peer, dst, received);
                        return;
                    }

                    dst.flip();
                    received.complete(StandardCharsets.UTF_8
                            .decode(dst).toString());
                    closeQuietly(peer);
                }

                @Override
                public void failed(Throwable error, ByteBuffer dst) {
                    received.completeExceptionally(error);
                    closeQuietly(peer);
                }
            });
        } catch (Throwable error) {
            received.completeExceptionally(error);
            closeQuietly(peer);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        CompletableFuture<String> serverReceived =
                new CompletableFuture<>();
        CompletableFuture<Void> clientConnected =
                new CompletableFuture<>();

        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open()
                             .bind(new InetSocketAddress(loopback, 0));
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            listener.accept(null,
                    new CompletionHandler<AsynchronousSocketChannel, Void>() {
                @Override
                public void completed(
                        AsynchronousSocketChannel peer, Void attachment) {
                    readFour(peer, ByteBuffer.allocate(4), serverReceived);
                }

                @Override
                public void failed(Throwable error, Void attachment) {
                    serverReceived.completeExceptionally(error);
                }
            });

            client.connect(listener.getLocalAddress(), null,
                    new CompletionHandler<Void, Void>() {
                @Override
                public void completed(Void result, Void attachment) {
                    clientConnected.complete(null);
                }

                @Override
                public void failed(Throwable error, Void attachment) {
                    clientConnected.completeExceptionally(error);
                }
            });

            clientConnected.get(3, TimeUnit.SECONDS);

            ByteBuffer request = StandardCharsets.UTF_8.encode("PING");
            while (request.hasRemaining()) {
                client.write(request).get(3, TimeUnit.SECONDS);
            }

            String received = serverReceived.get(3, TimeUnit.SECONDS);
            System.out.println("Connect callback: completed");
            System.out.println("Accept/read callback: " + received);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 AsyncHandlerDemo.java
java AsyncHandlerDemo
~~~

Stdout when the operations complete successfully:

~~~text
Connect callback: completed
Accept/read callback: PING
~~~

### What the Callback Demo Proves

- **accept handler** receives the **accepted AsynchronousSocketChannel**, without needing a dedicated thread calling blocking accept.
- **connect handler** receives **Void** on the success path and **Throwable** on the failure path. **finishConnect()** is not called.
- **read handler** receives an **Integer** indicating the number of bytes just read, not the whole message. If the buffer still has room, **readFour** initiates the next operation **after** the previous callback has run; it does not overlap a pending read.
- **readFour** keeps the same ByteBuffer across the callback chain for one connection. The buffer is only **flipped** once all 4 bytes have arrived.
- If EOF arrives before 4 bytes, **CompletableFuture.completeExceptionally(...)** reports the error and the peer is closed.
- Main uses **CompletableFuture.get(timeout)** only to wait for the final result and print in a fixed order. The callback path itself remains asynchronous. For a server with many clients, callbacks should not block waiting on a future that depends on the same thread group.
- This is a **one-connection, one-request** model; the callback only receives the request and closes the peer. A real server needs replies, accept re-arming, client limits, I/O timeouts, and an explicit state object, rather than using demo code in production.

**Java 17 Note:** **CompletableFuture** belongs to **java.util.concurrent** and helps coordinate completions; it does not by itself turn a blocking SocketChannel operation into an asynchronous one. In this example, **AsynchronousSocketChannel** itself actively initiates async read/connect/accept.

## 7. ByteBuffer and Partial I/O: Completing an Operation Does Not Mean Completing a Message

This is where NIO.2 applications most commonly go wrong: an operation completes and the callback invokes **completed(n, attachment)**, but **n is only the number of bytes transferred in that single batch**. If a 10 KiB message is expected, having the first read completion receive only 300 bytes is completely valid. Having a write transfer only 600 bytes is also completely valid.

~~~text
Message 1000 bytes
    |
    +-- read callback #1: 230 bytes
    +-- read callback #2: 400 bytes
    +-- read callback #3: 370 bytes
    |
    +-- total = 1000; only then parse the complete message
~~~

Rules:

- **Buffer position** advances by the byte count when the operation completes; **limit** stays unchanged. Only parse/decode received data after the operation has completed and framing is satisfied.
- With **ByteBuffer.allocate(N)**, before reading, position = 0 and limit = N. Once N bytes are received, call **flip()** to switch to reading from byte 0.
- When writing from a ByteBuffer, **write(src)** may write only part of it; check **src.hasRemaining()** and continue the operation after completion. Do not call **clear** while unsent bytes remain.
- **read result -1** means end-of-stream on the receive direction; if the protocol expects N bytes and only a partial message arrived, that is an incomplete message, not automatically a success.
- With async read/write, **do not modify or reuse a ByteBuffer until the operation using it finishes**. The Javadoc emphasizes that buffers are not safe for concurrent access by multiple threads while pending.
- **One pending read + one pending write** on the same channel is valid; two pending reads or two pending writes in the same direction cause ReadPendingException/WritePendingException.
- **Scattering read/gathering write** optimizations have overloads that read/write a **ByteBuffer array** with a **Long** result callback; you must still check the transferred byte count and array bounds.

Illustrative snippet for sending an entire ByteBuffer via callback, **not a standalone file** (assuming channel, buffer, and completion handler already exist):

~~~java
channel.write(buffer, buffer,
        new CompletionHandler<Integer, ByteBuffer>() {
    @Override
    public void completed(Integer n, ByteBuffer pending) {
        if (pending.hasRemaining()) {
            channel.write(pending, pending, this);
        } else {
            onMessageSent();
        }
    }

    @Override
    public void failed(Throwable error, ByteBuffer pending) {
        onWriteFailed(error);
    }
});
~~~

In this snippet, **onMessageSent()** and **onWriteFailed(...)** are application-defined; the callback chain must keep the buffer in the attachment/state, catch synchronous exceptions when initiating a new operation, and enforce deadlines/cancellation. Do not infer from a **write completed** callback that the remote application has processed the request: it only reflects local I/O under the channel contract.

## 8. ReadPendingException, WritePendingException, and AcceptPendingException

Several async channel limits are **invariants that must be designed around from the start**, not just rare errors:

| Object | Outstanding I/O limit | If called concurrently |
|---|---|---|
| **AsynchronousServerSocketChannel** | At most **one pending accept** on the listener | **AcceptPendingException** |
| **AsynchronousSocketChannel** | At most **one pending read** on the connection | **ReadPendingException** |
| **AsynchronousSocketChannel** | At most **one pending write** on the connection | **WritePendingException** |
| **AsynchronousSocketChannel** | **One read** and **one write** can be pending simultaneously | Valid for full-duplex TCP |

### Pitfall: One Connection, Two Workers Reading Simultaneously

For example, worker A initiates **channel.read(bufferA)** and the callback has not run yet; worker B simultaneously calls **channel.read(bufferB)**. B can hit **ReadPendingException**. Do not patch this with an immediate retry loop; design **a single read owner/state machine** for the connection and dispatch results to the appropriate requests.

### Pitfall: Multiple Messages Calling Write Simultaneously

Do not let multiple threads perform **channel.write(buffer)** independently on the same connection without a coordinator. While the first write is still pending, a second write causes **WritePendingException**, or the application loses message ordering. Use a **per-connection outgoing buffer queue**, initiating the next write only after the previous operation completes, with byte/queue-depth limits and backpressure.

### Pitfall: Re-Arming Accept Too Early

While listener.accept is pending, do not start another accept on the same listener. Inside the **completed** callback, the previous operation has finished and you can re-arm; you must still catch errors and avoid re-arming during shutdown. Do not create a task that retries AcceptPendingException in a busy CPU loop.

## 9. Timeout, Deadline, and Cancellation Are Not the Same Concept

**AsynchronousSocketChannel** has read/write overloads that take a per-operation timeout with **CompletionHandler**, such as:

~~~java
channel.read(buffer, 2, TimeUnit.SECONDS, requestState,
        new CompletionHandler<Integer, RequestState>() {
    @Override
    public void completed(Integer n, RequestState state) {
        // Operation completed before timeout.
    }

    @Override
    public void failed(Throwable error, RequestState state) {
        // May be InterruptedByTimeoutException.
    }
});
~~~

**This is an illustrative snippet**, with a custom RequestState; it is not a standalone program. You must distinguish:

| Mechanism | Guarantee / Effect |
|---|---|
| **Future.get(2, SECONDS)** | Caller waits at most about 2 seconds; **TimeoutException does not guarantee the operation was canceled or the channel was closed** |
| **read/write(..., timeout, unit, attachment, handler)** | Per-**operation** timeout per the API; completion fails with **InterruptedByTimeoutException** on expiration |
| **Overall request deadline** | Application policy: covers connect, accept, read/write, parsing, business processing, and response |
| **Future.cancel(...)** | Requests Future cancellation per contract; you must not assume all bytes/side effects were rolled back |
| **channel.close()** | Closes the channel to stop using it and release resources; pending operations may complete with failure |
| **group.shutdown()/shutdownNow()** | Manages channel/thread group lifecycle, does not replace per-connection timeouts |

**Serious pitfall of read/write timeouts:** Java 17 Javadoc states that if an operation times out, **the state of the associated ByteBuffer may be undefined** and the provider may put the channel's I/O direction into an **implementation-specific error state** if it cannot guarantee bytes were not read/written. Therefore, **do not blindly retry with the same buffer on the same channel** after InterruptedByTimeoutException. For protocols needing deterministic state, usually **close the channel, discard the associated buffer, and create a new session/connection**, or follow the specific provider contract if well understood.

**TimeoutException from Future.get** only proves that *the waiting thread timed out*, not that I/O did not occur. If code continues reusing the ByteBuffer while the old operation is still pending, it can violate ownership and corrupt data. Cancel/close according to policy before reusing state; avoid assuming cancel always prevents the remote peer from receiving bytes.

### Connect and Accept Timeouts

- **AsynchronousSocketChannel.connect(...)** does not have a timeout-accepting overload in this API. You can wait on the Future with an external deadline and then **close the channel on expiration**, or coordinate via a scheduler/CompletableFuture and close unfinished connections per policy.
- **AsynchronousServerSocketChannel.accept(...)** has no timeout overload similar to timed read/write. If waiting via **acceptFuture.get(timeout)**, the timeout only bounds the caller; the listener may still be accepting. Do not initiate a new accept while the old operation is still pending.
- **System.nanoTime()** is suitable for measuring **elapsed durations**; do not use System.currentTimeMillis for deadlines because wall-clock time can shift. Use a **remaining budget** across sequential operations instead of granting a fresh 5 seconds each time.
- **DNS/name resolution** may occur before asynchronous connect is initiated, depending on how you construct InetSocketAddress. In real systems, include DNS and TLS/auth handshakes in the total deadline.

**Overly tight timeouts and unbounded retries** can cause connection storms or server overload. Use bounded retry counts, exponential backoff + jitter, pending connection limits, latency observability, and clear idempotency guarantees if clients resend requests with side effects.

## 10. AsynchronousChannelGroup: Thread Pool and Ownership

Channels can use the **JVM default group** via **open()**, or an application-created group via **open(group)**. **AsynchronousChannelGroup** manages the resources needed to process I/O completions and dispatch handlers, along with the associated thread pool.

~~~text
AsynchronousChannelGroup
    |
    +-- thread pool / completion dispatch
    |
    +-- AsynchronousServerSocketChannel (listener)
    |
    +-- accepted AsynchronousSocketChannel(s)
    |
    +-- AsynchronousSocketChannel client(s)
~~~

Example of creating a group in Java 17, **illustrative code snippet**:

~~~java
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(
                4, runnable -> new Thread(runnable, "async-io"));

try (AsynchronousServerSocketChannel server =
             AsynchronousServerSocketChannel.open(group)) {
    server.bind(new InetSocketAddress(0));
    // Open AsynchronousSocketChannel.open(group) if needed.
    // Initiate and complete operations before cleaning up resources.
} finally {
    group.shutdown();
    group.awaitTermination(5, TimeUnit.SECONDS);
}
~~~

The snippet above assumes imports are present and is not a standalone file. You must close **all accepted/client channels** belonging to the group (if any), wait for callbacks to finish, and check the return value of awaitTermination. **AsynchronousChannelGroup is not AutoCloseable** in Java 17; use **shutdown** and **awaitTermination**, and do not place the group directly in try-with-resources.

### Which Group Does Each Accepted Channel Belong To?

If a listener is opened in an **AsynchronousChannelGroup**, the listener's accepted AsynchronousSocketChannels also belong to the **same group**. This keeps resource management clear, but also means **heavy callbacks** on the group can affect other connections.

### shutdown and shutdownNow

- **group.shutdown()** initiates an orderly shutdown: prevents creating new channels bound to the group; the group only terminates once associated channels are closed, running callbacks finish, and resources are released.
- **group.shutdownNow()** stops more forcefully, closing channels in the group; pending operations may fail.
- **group.awaitTermination(...)** waits for the group to terminate and may block the calling thread; check the boolean return value.
- **Do not shut down the group-owned executor directly** elsewhere in the application; the group documentation warns that terminating the executor directly can result in undefined behavior.
- **Do not use a very small fixed pool and then call get() waiting on another future inside a callback on the same pool**: this can cause starvation or deadlock. Keep completion dispatching brief and offload CPU/blocking business tasks to a separate bounded executor.

**There is no rule that every OS uses the same implementation.** The NIO.2 API provides an async contract, while providers may use native mechanisms or I/O helper threads depending on the platform. Do not assume async uses zero threads or is always faster than blocking I/O.

## 11. Reliable Lifecycle and Cleanup

A production design should distinguish **listener lifecycle**, **accepted connection lifecycle**, and **request lifecycle**:

1. The listener binds and starts one pending accept.
2. When accept completes, check the shutdown policy; if still accepting load, re-arm accept.
3. Attach a **ConnectionContext** to the accepted channel: parser, outgoing queue, ByteBuffer ownership, read/write pending flags, authentication status, deadline, byte counters, request IDs.
4. Run one read chain per connection and at most one write chain; both directions can operate concurrently.
5. When a complete message arrives, validate/frame it and hand off business processing to an appropriate pool; bound active tasks and queues.
6. When a response arrives, enqueue its ByteBuffer onto the write queue and trigger the write chain if no writer is active.
7. On error, EOF, timeout, or cancellation: complete the Future/response once, close the channel, release buffers and state, and decrement active-connection metrics.
8. On server shutdown: stop re-arming accept, close the listener, drain/close accepted clients within a deadline, then shut down the group if owned by the server.

**Closing the listener does not automatically close all accepted peers.** Close each accepted AsynchronousSocketChannel and release its attachment/state. With the default group, applications usually do not directly shut down the entire JVM default group; they only close the channels they own. If you create a dedicated group for the server, manage group termination explicitly.

**Closing a channel does not guarantee all callbacks have finished by the time close returns.** Design callbacks around **OPEN/CLOSING/CLOSED** states, avoid starting new operations while closing, and use appropriate atomics/locks to prevent double completion or double resource release.

## 12. Common Errors and Exceptions

| Error / Exception | Common cause | How to handle |
|---|---|---|
| **AcceptPendingException** | Calling accept twice while the first is still pending on the listener | Single accept owner; re-arm upon completion |
| **NotYetBoundException** | accept before bind | Bind the listener before calling accept |
| **NotYetConnectedException** | read/write on an async client that has not finished connecting | Wait for connect completion |
| **ConnectionPendingException** | New connect while an earlier connect is still pending | Do not start a second connect; wait/cancel/close in a controlled way |
| **AlreadyConnectedException** | Reconnecting an already connected channel | Reuse the connection for I/O; do not reconnect |
| **ReadPendingException** | Two reads pending on one channel | Serialize the read chain |
| **WritePendingException** | Two writes pending on one channel | Serialize the write queue |
| **InterruptedByTimeoutException** | Timed async read/write expired | Treat channel/buffer state as undefined; usually close and handle error |
| **ExecutionException** | Future.get received a failed operation result | Inspect getCause(), do not swallow errors |
| **TimeoutException** | Future.get(timeout) wait expired | Do not assume the operation was canceled; clean up per policy |
| **ClosedChannelException / AsynchronousCloseException** | Channel closed while an operation was in progress | Handle cancellation/cleanup normally if shutting down |
| **ShutdownChannelGroupException** | Group shut down/terminated when trying to open or initiate I/O | Do not enqueue new operations; close resources |
| **EOF: read returns -1** | Peer closed its sending direction | Handle framing and half-close per protocol; not an exception by default |

**IOException may be reported via Future or CompletionHandler.failed**, rather than necessarily thrown synchronously at the async operation call site. However, some precondition errors (unbound, already pending, invalid buffer, closed group...) may be thrown **immediately upon initiation**. Therefore, a proper callback path must handle **both synchronous initiation exceptions and asynchronous completion failures**.

**Do not catch and ignore every Throwable in callbacks.** Errors must be reported to the request coordinator, logged with sufficient context, and trigger resource cleanup. For severe errors, follow the system's monitoring and crash policy rather than continuing in an uncontrolled state.

## 13. Performance Characteristics and Overload Risks

The asynchronous API avoids one blocking thread per connection in many architectures, but bottlenecks can still occur in:

- **Completion handler processing time**, especially when callbacks run blocking DB queries, decode overly large payloads, or wait on another Future on the same pool.
- **Number of accepted connections**: each peer consumes kernel resources, buffers, and Java objects; async does not make FDs/network memory infinite.
- **Bytes queued for writing**: an unbounded write queue leads to growing heap/direct memory and latency.
- **Unbounded message reads**: if a server accumulates payloads from slow clients without byte limits, there is a DoS risk.
- **AsynchronousChannelGroup thread pool** mismatched to the workload; completion callbacks suffer starvation or resource contention.
- **Tangled timeouts and cancellation**: operations no longer awaited by callers still keep buffers alive or channels unclosed.
- **Framing/TLS/auth**: async TCP must still define message boundaries, authentication, and appropriate encryption protocols (TLS typically requires SSLEngine or a battle-tested library).

Metrics to collect: **active accepted channels**, accepts/second, **pending accepts**, **outstanding reads/writes per connection**, bytes in/out, write queue depth, completion latency, callback duration, group thread utilization, connection/operation timeouts, EOF/error rates, p95/p99 request latency, and closed channel counts.

For backpressure, you can pause initiating new reads on a connection when the business queue is too full, rate-limit input per connection/tenant, cap message size and write queue depth, and apply admission control to accepted clients. Do not just blindly increase thread counts or pending operations.

## 14. Subtle Programming Mistakes to Avoid

### 14.1. Reading and Writing the Same ByteBuffer Without Synchronization

A Buffer's position may be updated by the provider while an async operation is pending. If another thread calls **flip/clear/put** on that buffer, payload data or bookkeeping can be corrupted. Maintain **single-operation/buffer ownership**, reusing or transferring ownership only after completion.

### 14.2. Future.get Timeout Followed by Forgetting to Close the Connection

**Future.get(timeout)** bounds the waiting thread; it does not automatically close the channel. If it throws TimeoutException and the caller abandons the Future and reuses the buffer, the old operation can still complete and overwrite repurposed data. Close/cancel per contract, wait for cleanup when needed, and do not promise that packets/bytes have not reached the remote peer.

### 14.3. Closing the Listener and Forgetting Accepted Peers

AsynchronousServerSocketChannel owns the **listener**, whereas accept returns channels for individual connections. If the server stops without a registry of accepted connections, they may stay alive or leak resources. Track and close each peer.

### 14.4. Calling Accept Concurrently from Multiple Threads

One listener allows only **one pending accept**. Do not have multiple workers call accept indiscriminately; wait for completed and then re-arm, or use a single accept coordinator. To scale a server, increase listeners/instances according to architecture and OS rather than trying to break the contract.

### 14.5. Assuming Async Callbacks Run on a Single Event Loop

Completion handlers execute via **AsynchronousChannelGroup** and may run on different threads; ordering between callbacks of independent operations is not guaranteed like a single-threaded loop. Concurrent state must be thread-safe, especially if a read callback and a write callback mutate the same connection context.

### 14.6. Treating completed(n) as "A Full Message"

The count n is only the bytes transferred in one read/write call; keep the ByteBuffer, check **hasRemaining**, framing, and EOF. On a stream, you cannot assume client.write(1024) corresponds to a single server.read(1024) callback.

### 14.7. Not Handling failed and Synchronous Initiation Exceptions

**Completed** may never fire if the operation fails; errors go to **failed** or are thrown synchronously before the operation starts. Do not leave CompletableFuture/callers waiting forever by forgetting to signal the error path.

### 14.8. Missing Read Deadlines or Write Queue Limits

A client that sends 1 byte and stops can keep a read operation pending for a very long time. Use timed reads and an overall request deadline, accepting that timeouts can leave buffer state undefined; close when appropriate. For slow-reading clients, the server's response queue can fill up; apply backpressure and memory limits.

## 15. Choosing NIO.2 Asynchronous or Another Model?

| Scenario | A reasonable choice | Reason |
|---|---|---|
| Learning Java's completion-style TCP API | **AsynchronousServerSocketChannel/AsynchronousSocketChannel** | Clear Future and CompletionHandler model |
| Few connections, simple sequential I/O | **Blocking Socket/ServerSocket** | Easy to develop and debug |
| Many connections, already using a Selector event loop | **SocketChannel + Selector** | Direct control over readiness, buffers, and scheduling |
| Using Java 21+ with lots of blocking I/O | Consider **virtual threads** | Easy-to-follow sequential programming model; still needs timeouts/limits |
| Services with complex framing, TLS, backpressure | Battle-tested networking framework | Avoids reimplementing multiple protocol layers |

There is no rule that **async is always faster than blocking**. You must measure based on workload type, connection count, callback characteristics, CPU/GC, provider mechanics, and OS. NIO.2 asynchronous offers a different completion API than Selector; the right tool depends on state-management requirements and system complexity.

## 16. Hands-On Exercises

### Exercise A — Future and Length Limits

Run **AsyncFutureEchoDemo.java**. Change the request to a 1,024-byte UTF-8 string; replace the fixed buffer with a **4-byte length-prefix** protocol, reading the header first and then reading the exact payload within a limit. Explain why you cannot infer from a single Future.read return that the full message has arrived.

### Exercise B — Partial Callback Reads

Run **AsyncHandlerDemo.java**, change the buffer from 4 to 8 bytes, and have the client send all 8 bytes. Ensure the callback only completes the CompletableFuture after all bytes are read; if the peer closes earlier, completeExceptionally instead of decoding a truncated message.

### Exercise C — Two Pending Reads

On a connected AsynchronousSocketChannel, initiate a first read waiting for bytes, then try initiating a second read. Observe **ReadPendingException** per the Java API and refactor the architecture into a single read chain that owns buffer management.

### Exercise D — Operation Timeout vs. Wait Timeout

Compare **Future.get(100, MILLISECONDS)** with **channel.read(buffer, 100, MILLISECONDS, attachment, handler)**. Explain why the former only bounds the caller's wait, while the latter fails completion with InterruptedByTimeoutException and can leave buffer/channel state undefined. Do not reuse a buffer that still has a pending old operation.

### Exercise E — Re-Arming Accept

Starting from AsyncHandlerDemo, build a continuous listener: each time the accept callback completes, re-arm a new accept and then handle the newly received peer. Add a maximum active connections cap and a shutdown flag; when stopping, do not re-arm and close all held peers.

### Exercise F — AsynchronousChannelGroup

Open a fixed four-thread group, attach the listener/client to that group, and log the thread name inside callbacks (without assuming specific names or order). Experiment with an intentionally blocking callback and observe throughput drop; then move blocking business logic to a bounded worker pool. Use shutdown/awaitTermination following the proper lifecycle.

### Exercise G — Write Queue and Backpressure

Create a very slow-reading client and a server generating many continuous responses. Organize a byte-bounded outgoing ByteBuffer queue; do not initiate a second write before the previous write completes. Measure write latency and queue depth. When thresholds are exceeded, reject or pause production per policy instead of buffering unboundedly.

### Exercise H — Error Paths and Cleanup

Close the client immediately while the server is reading; check whether read returns -1 or fails depending on timing. Try closing the listener while an accept is pending; ensure callbacks/futures report errors and no accepted channels leak. When connecting to an unserved endpoint, handle errors in Future/failed, close the channel, and do not retry unboundedly.

## 17. Comprehension Check Questions

**1. Does AsynchronousServerSocketChannel read client data directly?** No. It is a listener; accept returns an **AsynchronousSocketChannel** for reading/writing a specific connection.

**2. Does Future<Void>.get() for connect return true?** No; the result type is **Void**, and a successful get returns **null**.

**3. Can a listener have two pending accepts?** No. Per the API, this throws **AcceptPendingException**.

**4. Can one read and one write be pending concurrently on the same async connection?** Yes. However, you must not have two pending reads or two pending writes at the same time.

**5. Does CompletionHandler.completed(n) mean "a full message was read/written"?** No. **n** is only the byte count for that *operation*; you must check remaining bytes and framing.

**6. Do callbacks always run on the thread that initiated the operation?** No. They are dispatched via the group; state-handling code must be concurrency-safe.

**7. Does Future.get(timeout) guarantee the read was canceled on timeout?** No. It bounds the caller's wait; the operation may remain pending.

**8. Is it always safe to retry with the same ByteBuffer after a timed async read/write expires?** No. Java 17 warns that the buffer may be in an undefined state and the channel may be in an implementation-specific error state.

**9. Does AsynchronousSocketChannel use Selector OP_CONNECT and finishConnect?** No. That is the **SocketChannel** model; async connect notifies via Future/CompletionHandler.

**10. Does group.shutdown() immediately close all channels?** No. Orderly shutdown waits for associated channels to close and callbacks to finish; **shutdownNow()** is more forceful.

**11. Are accepted channels closed automatically when listener.close() is called?** You should not assume so; manage and close accepted peers separately.

**12. Does asynchronous I/O eliminate the need for threads, backpressure, or framing?** No. It changes how I/O is awaited, without removing OS/thread/memory limits or protocol design responsibilities.

## Official Reference Documentation

- Java SE 17 — **AsynchronousServerSocketChannel**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html
- Java SE 17 — **AsynchronousSocketChannel**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html
- Java SE 17 — **AsynchronousChannelGroup**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html
- Java SE 17 — **CompletionHandler**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html
- Java SE 17 — **ByteBuffer**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html

**Remember:** **AsynchronousServerSocketChannel** accepts connections via asynchronous **accept** and returns an **AsynchronousSocketChannel** for each peer; **AsynchronousSocketChannel** performs **connect/read/write** with **Future** or **CompletionHandler**. Do not overlap multiple accepts/reads/writes in the same direction; do not modify a ByteBuffer while an operation is pending; always handle partial I/O, errors, EOF, and timeouts. **Future.get() can block the caller, timed read/write can leave buffer/channel state undefined, and heavy callbacks can stall the group.** Proper design requires framing, deadlines, bounded queues, ownership, cleanup, and load observability.
