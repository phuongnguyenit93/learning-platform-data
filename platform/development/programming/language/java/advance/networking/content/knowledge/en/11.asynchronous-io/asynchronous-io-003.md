# Receiving Results via Future or CompletionHandler in Java Asynchronous I/O

With Java NIO.2, an application can **initiate an I/O operation before the operation completes**, and then receive the result later using two main styles: **`Future<V>`** or **`CompletionHandler<V,A>`**. Both are supported by asynchronous channels such as `AsynchronousSocketChannel`, `AsynchronousServerSocketChannel`, and `AsynchronousFileChannel`, but they differ significantly in how program control flow is managed:

- **`Future<V>`:** the method immediately returns an object representing the future result. The caller can continue doing other work, and then call `get()` when the result is actually needed. **`get()` can block the calling thread**.
- **`CompletionHandler<V,A>`:** the caller passes a callback right when initiating I/O. Upon completion, the system invokes `completed(result, attachment)` or `failed(error, attachment)`. This style is well-suited for chaining asynchronous tasks without needing a thread waiting for each result.

In this lesson, the main example uses **TCP loopback** with `AsynchronousServerSocketChannel` and `AsynchronousSocketChannel`, since this module focuses on networking. The final section also shows how to apply the same model to `AsynchronousFileChannel`. All standalone runnable code is written for **Java 17 or later**.

## 1. “Asynchronous” Does Not Mean `get()` Never Blocks

An asynchronous operation is typically split into three stages:

~~~text
T0 — CALL: initiate read / write / connect / accept
         |
         +--- Future<V> is returned
         |       application processes other work
         |       ...
         |       get() waits if not yet completed
         |
         +--- OR register CompletionHandler
                 application yields control
                 ...
                 completed(value, attachment)
                    or failed(cause, attachment)

T1 — I/O actually completes or fails
T2 — Application consumes result / handles error / cleans up resources
~~~

The difference is not that “one uses async and the other uses sync”: both **initiate** asynchronous I/O. However, if right after `channel.read(buffer)` you call `future.get()` on the same thread, you have **synchronously waited** for the result at that point. Waiting may be reasonable in a small program, but when building a server serving many clients, you should avoid letting every thread be occupied just by calling `get()`.

Java NIO.2 channels may use threads from an `AsynchronousChannelGroup` and OS-specific I/O mechanisms; you should not infer that every runtime implements them using the exact same kernel mechanism. **“Asynchronous” is an API contract**, not a promise that the operation uses no threads, never blocks at any level, or is always faster than blocking I/O.

## 2. Which APIs Return Future, and Which Accept CompletionHandler?

For TCP asynchronous channels in Java 17:

| Operation | Future form | Callback form |
| --- | --- | --- |
| Server accepts connection | `Future<AsynchronousSocketChannel> accept()` | `accept(A attachment, CompletionHandler<AsynchronousSocketChannel, ? super A>)` |
| Client connects TCP | `Future<Void> connect(SocketAddress remote)` | `connect(SocketAddress, A, CompletionHandler<Void, ? super A>)` |
| Read bytes | `Future<Integer> read(ByteBuffer dst)` | `read(ByteBuffer dst, A, CompletionHandler<Integer, ? super A>)` |
| Write bytes | `Future<Integer> write(ByteBuffer src)` | `write(ByteBuffer src, A, CompletionHandler<Integer, ? super A>)` |

`AsynchronousSocketChannel` reads and writes a **TCP byte stream**, and does not automatically delimit one `read()` to correspond to one request, one response, or one `write()`. The read/write result is typically **the number of bytes transferred in that completion**, which may be smaller than the number of bytes you expected.

With `AsynchronousFileChannel`, both styles also exist, but the API additionally takes a position in the file:

~~~java
// Abbreviated signatures (illustrative, not a standalone runnable class):
Future<Integer> result = file.read(dst, filePosition);

file.read(dst, filePosition, attachment,
          new CompletionHandler<Integer, AttachmentType>() {
              @Override
              public void completed(Integer count, AttachmentType state) {
                  // Read completed.
              }
              @Override
              public void failed(Throwable cause, AttachmentType state) {
                  // Read failed.
              }
          });
~~~

In `AsynchronousFileChannel`, the file position is an **explicit parameter**; unlike a TCP socket, which is a sequential stream and has no file offset. This snippet only illustrates the API; you must open a file channel and define `AttachmentType` before compiling.

## 3. Receiving Results with `Future<V>`

Example:

~~~java
// Fragment inside a method that has AsynchronousSocketChannel channel:
ByteBuffer buffer = ByteBuffer.allocate(1024);
Future<Integer> pendingRead = channel.read(buffer);

// You can perform work independent of pendingRead here.
int bytes = pendingRead.get(); // Blocks if the read has not completed yet.
buffer.flip();
~~~

Here:

1. `read(buffer)` **initiates the read operation** and returns a `Future<Integer>`.
2. `pendingRead.isDone()` indicates that the operation **has terminated** in some state, which does not necessarily mean it succeeded. It may have succeeded, failed, or been cancelled.
3. `pendingRead.get()` waits for the result if needed. For a successfully completed read, the `Integer` value represents the number of bytes read; `-1` indicates EOF from the TCP peer's output side.
4. Only after completion may you use or manipulate the buffer as if that I/O is finished. `flip()` switches the buffer from receiving mode to reading mode.

**Note:** for a `ByteBuffer` with `remaining() == 0`, a read call may complete immediately with `0`. Do not treat `0` as proof of a lost connection. When `remaining() > 0`, a normal TCP read may return only part of the desired data; you must use framing or loop until enough bytes / delimiter / EOF are received.

### Using `get(timeout, unit)` Properly

~~~java
// Fragment for an already initiated Future<Integer>.
try {
    Integer n = pendingRead.get(3, TimeUnit.SECONDS);
    // n is the byte count or -1; continue processing per protocol.
} catch (TimeoutException timeout) {
    // ONLY times out waiting for the Future on the current thread.
    // Does NOT automatically cancel the pending I/O.
    channel.close(); // Example cancellation policy by closing the channel.
}
~~~

`get(3, SECONDS)` limits **the wait time of the get call**. If it throws `TimeoutException`, the I/O operation may **still be in progress**; a `Future.get` timeout does not automatically send a stop signal to the OS and does not automatically turn the operation's outcome into a failure.

If the application no longer wants to keep the operation, it can use `Future.cancel(...)` according to the channel's specific contract; however, for asynchronous sockets, cancellation can affect the channel's state and bytes that have been or are being transferred. Do not assume `cancel(true)` always interrupts immediately without side effects. **Controlled channel closing/resource release** and not reusing a buffer whose operation outcome is uncertain is a simpler policy in many session-abandonment cases.

### Important Exceptions of Future

| Situation | Manifestation | Interpretation |
| --- | --- | --- |
| I/O completes successfully | `get()` returns `V` | Check the result value; byte count may be smaller than the payload |
| I/O fails | `ExecutionException` | Actual cause is in `getCause()`, usually `IOException` or a channel error |
| Waiting thread is interrupted | `InterruptedException` | Restore the interrupt flag if handled at an appropriate layer; organize cleanup |
| `get(timeout)` expires | `TimeoutException` | Wait timed out; I/O is not automatically cancelled |
| Future has been cancelled | `CancellationException` | No normal successful result |

Error handling example:

~~~java
// Illustrative fragment; requires java.util.concurrent.* imports.
try {
    int n = readFuture.get(5, TimeUnit.SECONDS);
    if (n == -1) {
        // TCP peer closed its sending direction.
    } else {
        // n bytes have been written into ByteBuffer.
    }
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    // Log cause with client/request context, not just the wrapper.
    throw new IOException("Asynchronous read failed", cause);
} catch (TimeoutException ex) {
    // Decide to close connection / drop response / retry per business logic.
    throw new IOException("Read did not finish in time", ex);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IOException("Waiting thread interrupted", ex);
}
~~~

This is a **fragment**, assuming `readFuture` already exists and `IOException` is imported. In a real system, besides rethrowing the error, you also need to manage the channel lifecycle, cancel when appropriate, and avoid using a timed-out operation in a way that creates a race.

## 4. Receiving Results with `CompletionHandler<V,A>`

Java NIO.2 definition:

~~~java
public interface CompletionHandler<V, A> {
    void completed(V result, A attachment);
    void failed(Throwable exc, A attachment);
}
~~~

Where:

- `V` is the **I/O result type**: for example `Integer` for read/write, `Void` for connect, or `AsynchronousSocketChannel` for accept.
- `A` is the **attachment type**, meaning the context object **passed by you when calling I/O**, not a value Java automatically extracts from the buffer.
- `completed(...)` is invoked when the operation completes successfully; for a TCP read, a `completed(-1, ...)` callback is a successful completion **in terms of the API** indicating EOF, not `failed(...)`.
- `failed(Throwable, attachment)` is invoked when the I/O operation fails. This is where you receive the error cause directly, without having to unwrap `ExecutionException` as when calling `Future.get()`.
- Callbacks should complete quickly, avoiding long CPU/DB blocking work or calling `Future.get()` with an unbounded wait inside the callback, because doing so can reduce the number of threads in the asynchronous channel group available to dispatch other callbacks.

Example of a read operation:

~~~java
// Fragment inside a method, socket already connected.
ByteBuffer buffer = ByteBuffer.allocate(1024);

channel.read(buffer, "request-42",
        new CompletionHandler<Integer, String>() {
            @Override
            public void completed(Integer count, String requestId) {
                if (count < 0) {
                    // EOF, cleanup depending on protocol.
                    return;
                }
                buffer.flip();
                // Parse data associated with requestId.
                // If data is incomplete, schedule the next read after
                // the current operation has completed.
            }

            @Override
            public void failed(Throwable exc, String requestId) {
                // Log exception and requestId context, cleanup.
            }
        });
~~~

`"request-42"` is an attachment of type `String`. You can replace it with an object containing an ID, buffer, deadline, parser state, or request state. Avoid stuffing too much unsynchronized mutable global state into callbacks. Passing a different attachment does not make two overlapping read operations on the **same channel** valid.

### Callbacks Change How Task Chains Are Written

From the sequential waiting pattern:

~~~text
Future read -> get -> parse -> Future write -> get
     (thread waits)             (thread waits)
~~~

to the pattern of triggering the next step once the previous step completes:

~~~text
initiate read()
       |
       +--- completed(readBytes)
       |        |
       |        +--- parse; if request is complete, initiate write()
       |                                    |
       |                                    +--- completed(writeBytes)
       |                                    +--- failed(writeError)
       |
       +--- failed(readError)
~~~

In cases where a response needs multiple writes due to a partial write, `completed(writeCount)` checks `ByteBuffer.hasRemaining()` before registering the next write. Do not assume **one** successful write callback means the entire response has been written.

## 5. Java 17+ Example: Both Future and CompletionHandler on TCP Loopback

This complete example creates a TCP listener on loopback with port `0` so the OS picks an available port. It runs **two separate sessions**:

- **Future path:** the client connects to the listener and sends `PING`; the server receives all four bytes using `read(...).get(...)` calls and prints the result.
- **Handler path:** the client registers a read callback, the server registers a write callback, and the two handlers continue until their buffers are complete; the main thread only uses `CountDownLatch` to finish **the test** in an orderly way, rather than using `Future.get()` to receive read/write results in this path.

Save with the exact name **`AsyncResultsDemo.java`**:

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
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncResultsDemo {
    private static final long LIMIT_SECONDS = 5;

    // Each Future.get() has a maximum wait time for that operation.
    private static int writeAll(
            AsynchronousSocketChannel channel, ByteBuffer data)
            throws Exception {
        int total = 0;
        while (data.hasRemaining()) {
            int n = channel.write(data)
                    .get(LIMIT_SECONDS, TimeUnit.SECONDS);
            if (n <= 0) {
                throw new IOException("No write progress");
            }
            total += n;
        }
        return total;
    }

    private static int readAll(
            AsynchronousSocketChannel channel, ByteBuffer data)
            throws Exception {
        int total = 0;
        while (data.hasRemaining()) {
            int n = channel.read(data)
                    .get(LIMIT_SECONDS, TimeUnit.SECONDS);
            if (n < 0) {
                throw new EOFException("Peer closed too soon");
            }
            if (n == 0) {
                throw new IOException("No read progress");
            }
            total += n;
        }
        return total;
    }

    private static void futurePath() throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(loopback, 0));

            Future<AsynchronousSocketChannel> pendingAccept =
                    listener.accept();

            try (AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open()) {
                Future<Void> connecting =
                        client.connect(listener.getLocalAddress());
                connecting.get(LIMIT_SECONDS, TimeUnit.SECONDS);

                try (AsynchronousSocketChannel serverSide =
                             pendingAccept.get(
                                     LIMIT_SECONDS,
                                     TimeUnit.SECONDS)) {

                    int written = writeAll(
                            client,
                            StandardCharsets.UTF_8.encode("PING"));

                    ByteBuffer inbound = ByteBuffer.allocate(4);
                    int received = readAll(serverSide, inbound);
                    inbound.flip();

                    System.out.println("futureWriteBytes=" + written);
                    System.out.println("futureReadBytes=" + received);
                    System.out.println(
                            "futureText="
                                    + StandardCharsets.UTF_8.decode(
                                            inbound));
                }
            }
        }
    }

    private static void handlerPath() throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(loopback, 0));

            Future<AsynchronousSocketChannel> pendingAccept =
                    listener.accept();

            try (AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open()) {
                client.connect(listener.getLocalAddress())
                        .get(LIMIT_SECONDS, TimeUnit.SECONDS);

                try (AsynchronousSocketChannel serverSide =
                             pendingAccept.get(
                                     LIMIT_SECONDS,
                                     TimeUnit.SECONDS)) {

                    ByteBuffer input = ByteBuffer.allocate(4);
                    ByteBuffer output =
                            StandardCharsets.UTF_8.encode("PONG");

                    CountDownLatch finished = new CountDownLatch(2);
                    AtomicReference<Throwable> failure =
                            new AtomicReference<>();
                    AtomicInteger sent = new AtomicInteger();
                    AtomicInteger received = new AtomicInteger();

                    // Read handler: attachment is the buffer itself.
                    client.read(input, input,
                            new CompletionHandler<Integer, ByteBuffer>() {
                        @Override
                        public void completed(
                                Integer n, ByteBuffer buffer) {
                            if (n < 0) {
                                failed(new EOFException(
                                        "EOF before 4 bytes"), buffer);
                                return;
                            }
                            received.addAndGet(n);

                            if (buffer.hasRemaining()) {
                                client.read(buffer, buffer, this);
                            } else {
                                finished.countDown();
                            }
                        }

                        @Override
                        public void failed(
                                Throwable exc, ByteBuffer buffer) {
                            failure.compareAndSet(null, exc);
                            finished.countDown();
                        }
                    });

                    // Write handler: only continue writing after completion.
                    serverSide.write(output, output,
                            new CompletionHandler<Integer, ByteBuffer>() {
                        @Override
                        public void completed(
                                Integer n, ByteBuffer buffer) {
                            if (n < 0) {
                                failed(new IOException(
                                        "Unexpected write result"),
                                        buffer);
                                return;
                            }
                            sent.addAndGet(n);

                            if (buffer.hasRemaining()) {
                                serverSide.write(buffer, buffer, this);
                            } else {
                                finished.countDown();
                            }
                        }

                        @Override
                        public void failed(
                                Throwable exc, ByteBuffer buffer) {
                            failure.compareAndSet(null, exc);
                            finished.countDown();
                        }
                    });

                    // Only so main waits for the demo to finish and prints
                    // stdout in order without depending on callback timing.
                    if (!finished.await(
                            LIMIT_SECONDS, TimeUnit.SECONDS)) {
                        throw new TimeoutException(
                                "Callback did not finish");
                    }
                    if (failure.get() != null) {
                        throw new IOException(
                                "Callback failed", failure.get());
                    }

                    input.flip();
                    System.out.println(
                            "handlerWriteBytes=" + sent.get());
                    System.out.println(
                            "handlerReadBytes=" + received.get());
                    System.out.println(
                            "handlerText="
                                    + StandardCharsets.UTF_8.decode(
                                            input));
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        futurePath();
        handlerPath();
    }
}
~~~

Compile and run:

~~~bash
javac AsyncResultsDemo.java
java AsyncResultsDemo
~~~

**Expected output** on JDK 17+ when TCP loopback is allowed (logic verified with JDK):

~~~text
futureWriteBytes=4
futureReadBytes=4
futureText=PING
handlerWriteBytes=4
handlerReadBytes=4
handlerText=PONG
~~~

### Why the Result Is Reliable

1. The listener binds to the loopback address and port `0`; then `getLocalAddress()` is used so the client connects to the exact port that was opened, without guessing a port.
2. `listener.accept()` returns `Future<AsynchronousSocketChannel>`; `client.connect(...)` returns `Future<Void>`. In both paths, we use `get(timeout)` to **set up the test preconditions** and obtain the server-side channel.
3. In **futurePath**, the `writeAll/readAll` loops handle the case where a single I/O completion does not consume the whole buffer. Each `get(timeout)` waits for **one operation**. This simple code intentionally throws an exception if `n == 0` while the buffer still has space, instead of looping indefinitely.
4. In **handlerPath**, `read(input, input, handler)` and `write(output, output, handler)` use the `ByteBuffer` as the attachment. The callback is invoked with **the exact same object that was passed**; no global variable is needed to hold the current request.
5. If `buffer.hasRemaining()`, the callback starts **the next I/O turn after the previous one has completed**; this avoids having two reads or two writes outstanding at the same time. You can have **one read and one write** outstanding concurrently on the same `AsynchronousSocketChannel`.
6. `CountDownLatch(2)` is only used so the demo program knows **both the read and write callbacks have finished**, and then prints the byte counts in order. A real server would not use the main thread to wait for every client like this.
7. `try-with-resources` closes the client, the accepted socket, and the listener. When the test times out or throws an exception, the resource-closing blocks still run.

**Limitation:** although the example uses a fixed 4-byte protocol, TCP does not preserve message boundaries: over a real network, there must be a length prefix, delimiter, or explicit framing. Each callback may see only part of the data. A 4-byte loopback result does not prove that every network delivers data in exactly one read or one write.

**Production note:** calls that initiate a new read/write inside a callback can also throw an immediate runtime exception if the channel has been closed, another operation is in progress, or the channel group is shut down; you must catch these errors, ensure completion is reported exactly once, close/reclaim the connection, and avoid leaving requests hanging forever. Recursive callbacks are suitable for illustrating a small buffer; production pipelines should use a state machine and a fairness policy when data is large.

## 6. Callback Pattern for connect and accept, Without Future

In the demo above, the setup step was synchronized using `Future.get()` for reproducibility. However, connect/accept also support completion handlers directly.

Example **server fragment** illustrating an accept callback and continuing to listen:

~~~java
// Fragment: listener is already bound and open.
listener.accept(null,
        new CompletionHandler<AsynchronousSocketChannel, Void>() {
    @Override
    public void completed(
            AsynchronousSocketChannel client, Void ignored) {
        // Initiate the NEXT accept after the previous accept completes.
        listener.accept(null, this);

        // Hand off the new socket to application processing.
        // Ownership, timeout, read/write, and close must be defined.
        handleNewClient(client);
    }

    @Override
    public void failed(Throwable error, Void ignored) {
        // Log; check if listener is still open before deciding to accept again.
    }
});
~~~

`listener.accept(...)` cannot be called a second time while a previous `accept` is still pending; doing so causes Java to throw `AcceptPendingException`. Inside the `completed` callback, the previous operation has completed, so you can register the **next accept**. Avoid losing the listener due to an exception in `handleNewClient`; you need error management and closing of accepted sockets.

Example **client fragment** for asynchronous connect:

~~~java
// Fragment: client is a newly opened AsynchronousSocketChannel.
client.connect(remote, "connect-request-42",
        new CompletionHandler<Void, String>() {
    @Override
    public void completed(Void ignored, String requestId) {
        // TCP connect completed. Now start writing the request.
        startRequest(client, requestId);
    }

    @Override
    public void failed(Throwable error, String requestId) {
        // Log cause, mark request as failed, and close client.
    }
});
~~~

In TCP `connect()`, only after `completed` should connected I/O begin. For `AsynchronousSocketChannel`, calling read/write before being connected can throw `NotYetConnectedException`. These two fragments are not standalone runnable classes because helpers `handleNewClient`/`startRequest`, variables `listener/client/remote`, and lifecycle management are defined by the application.

## 7. Managing ByteBuffer While an Operation Is Pending

Both `Future` and `CompletionHandler` require attention to **`ByteBuffer` ownership**.

### Correct Read Pattern

~~~text
fresh buffer (position=0, limit=capacity)
   |
initiate async read(buffer)
   |
WAIT for operation completion (Future.get succeeds or completed callback)
   |
check byte count; -1 = EOF
   |
buffer.flip()  -> limit=position, position=0
   |
parse exact remaining() region
   |
buffer.clear() -> prepare for reuse, does NOT physically erase data
~~~

If reading with `Future`, you must **not** call `flip()` or modify `position/limit` while I/O is still pending. If using a callback, only read or modify the buffer after `completed` for that turn, or after error handling when you are sure no operation is still modifying the buffer. The asynchronous channels Javadoc explicitly states that buffers must not be accessed or modified while I/O is still in use, because content and position can change asynchronously.

When calling `write`:

~~~java
ByteBuffer out = StandardCharsets.UTF_8.encode("HELLO");
// encode() already returns a buffer with bytes ready to be read;
// Do NOT call flip() again here.
channel.write(out); // Future path: wait for result before reusing out.
~~~

With a buffer created via `allocate()` and then `put()`, you must call `flip()` **before** writing. With `StandardCharsets.UTF_8.encode(...)`, the buffer is already in reading position. A single `completed(count)` may write only part of the data: the rest stays in `out.remaining()`, so sending the entire response requires a subsequent write turn after completion.

### Large Data and Framing

TCP does not preserve write boundaries. For example, a client writes `HELLO` once, but the peer may read 2 bytes first and 3 bytes next, or read multiple requests at once into a larger buffer. A protocol can use:

- **Length prefix:** send a header containing the payload byte count; the receiver reads the full header and then the full payload; validate max length before allocating.
- **Delimiter:** mark boundaries with a newline or special character; enforce a length limit to prevent a client from sending unbounded data.
- **Fixed length:** a control protocol defines exactly 4 bytes or N bytes, as in the demo; you must read all N bytes or receive EOF/error.

If reading UTF-8, a single character may be split across multiple reads; you should not decode each chunk arbitrarily without a stateful decoder. For binary payloads, define byte order, field format, version, and length.

## 8. One Outstanding Read and One Outstanding Write; No Two Concurrent Reads

According to the `AsynchronousSocketChannel` Javadoc:

- There can be **one pending read and one pending write** on the same channel at the same time.
- If you start a **second read before the first read completes**, Java throws `ReadPendingException`.
- If you start a **second write before the first write completes**, Java throws `WritePendingException`.
- Operations from multiple threads require shared management of ownership, ordering, buffers, and lifecycle. A “thread-safe API” does not mean business requests are automatically ordered as expected.

Counterexample:

~~~java
// Illustrative fragment: do not rely on this pattern.
Future<Integer> first = channel.read(bufferA);
Future<Integer> second = channel.read(bufferB);
// If first is still pending, second throws ReadPendingException.
~~~

Do not try to solve this by merely checking `first.isDone()` and then reading again while ignoring races in multi-threaded code; you need a **read/write operation queue** or a serial executor per connection. Chained callbacks (issuing the next read from the `completed` callback of the previous read) are a straightforward way to maintain one operation per direction.

On the server side, `AsynchronousServerSocketChannel` similarly allows only **one pending accept at a time**. Use the accept callback to register the next accept and hand off the client for processing, rather than opening multiple pending accepts on the same channel.

## 9. Timeout: Future.get Differs from True I/O Timeout

There are two distinct types of timeouts:

| Type | API | When expired |
| --- | --- | --- |
| **Time the thread waits for the result** | `future.get(3, SECONDS)` | Throws `TimeoutException` to the waiting thread; operation is not automatically cancelled |
| **I/O deadline managed by the channel** | `channel.read(buffer, 3, SECONDS, attachment, handler)` or the corresponding write overload | Operation completes with failure via `failed(InterruptedByTimeoutException, ...)` per API contract |

An I/O timeout callback fragment:

~~~java
// Fragment for a connected AsynchronousSocketChannel.
ByteBuffer input = ByteBuffer.allocate(2048);

channel.read(input, 3, TimeUnit.SECONDS, input,
        new CompletionHandler<Integer, ByteBuffer>() {
    @Override
    public void completed(Integer bytes, ByteBuffer buffer) {
        if (bytes == -1) {
            // EOF.
            return;
        }
        buffer.flip();
        // Process bytes and decide whether to read again.
    }

    @Override
    public void failed(Throwable error, ByteBuffer buffer) {
        if (error instanceof InterruptedByTimeoutException) {
            // Channel/buffer may be in an uncertain state;
            // avoid continuing to use them blindly.
        }
        // Close/discard connection per application policy.
    }
});
~~~

For overloads with an I/O timeout, the Javadoc states that **a timeout can leave the channel or underlying connection in an inconsistent state**. If the implementation cannot guarantee that bytes have not been read or written, the next operation in that direction may throw an unspecified runtime exception. **The state of the `ByteBuffer` of a timed-out operation is undefined**; do not read, flip, or reuse it as if it had succeeded.

This is a crucial point: `get(timeout)` does not automatically cancel, whereas a timeout set **on the channel operation** can alter the state of the I/O and buffer. In both cases, production design needs a clear lifecycle: request deadlines, closing the channel when abandoning a session, reporting errors once, releasing resources, and deciding on retries.

Any `get(timeout)` call only limits **that single wait**. If you loop reading 1,000 times, each with 3 seconds, the total request can last much longer than 3 seconds. You need an **overall deadline** (e.g., using `System.nanoTime()` for remaining time), rather than resetting the timeout indefinitely every time another byte is read.

## 10. Key Differences to Remember Between Future and CompletionHandler

| Criterion | `Future<V>` | `CompletionHandler<V,A>` |
| --- | --- | --- |
| Receiving result | Caller actively calls `get()` | Channel/provider invokes `completed(V,A)` |
| Error reporting | `get()` throws `ExecutionException` wrapping the cause | `failed(Throwable,A)` receives the cause |
| Does it block threads? | Initiates async; **`get()` can block** | No need to call `get()` for that operation; callback should avoid blocking itself |
| Context | Variables/closures around `Future` | Attachment `A` is passed through to the callback |
| Chaining I/O | Easy to write sequential loop `get → read → get` | Easy to initiate the next turn inside `completed` |
| Partial read/write | Still must handle `ByteBuffer.remaining()` | Still must handle `ByteBuffer.remaining()` |
| Timeout | `get(timeout)` is a wait timeout | Has I/O timeout overloads, `failed` callback |
| Callback control | Using only Future needs no callbacks | Requires designing callbacks, errors, thread groups, state |
| Learning and debugging | Easy to read, stack trace follows the waiting thread | Event-driven, harder when many concurrent activities exist |
| Scaling connection count | Easy to accidentally occupy many threads due to `get` | Easier to keep waiting thread count low, but must manage backpressure |

There is no rule that “Future is always low-performance” or “CompletionHandler is always better.” For a small utility or when you already have a bounded worker pool, `Future.get` can be very easy to understand. For a server with many connections, callbacks are often a better fit because you do not need one thread waiting per client. In both approaches, designing deadlines, framing, and resource limits is what determines whether the system is resilient.

## 11. Distinguishing CompletionHandler from CompletableFuture

Java has two similarly named concepts:

- `java.nio.channels.CompletionHandler<V,A>` is the **callback interface** specific to the asynchronous channels API, with `completed` and `failed`, taking an attachment.
- `java.util.concurrent.CompletableFuture<T>` is a concrete class implementing `Future<T>` and `CompletionStage<T>`, supporting chaining such as `thenApply/thenCompose/handle/whenComplete`.

JDK 17 **does not automatically turn all** NIO.2 operations that take a `CompletionHandler` into a `CompletableFuture`. Applications can write an adapter: create a `CompletableFuture<V>`, invoke the channel with a handler, and then call `complete(value)` or `completeExceptionally(error)`. You must consider cancellation, channel closing, and buffer ownership, rather than assuming cancelling the `CompletableFuture` automatically cancels the underlying I/O.

Example **adapter fragment**:

~~~java
// Java 17+ fragment for a connected AsynchronousSocketChannel.
static CompletableFuture<Integer> readAsync(
        AsynchronousSocketChannel channel, ByteBuffer dst) {

    CompletableFuture<Integer> result = new CompletableFuture<>();

    channel.read(dst, null, new CompletionHandler<Integer, Void>() {
        @Override
        public void completed(Integer bytes, Void ignored) {
            result.complete(bytes);
        }

        @Override
        public void failed(Throwable error, Void ignored) {
            result.completeExceptionally(error);
        }
    });
    return result;
}
~~~

The snippet above illustrates **bridging the two APIs**, not complete production code: if initiating `channel.read(...)` throws an immediate exception, the adapter needs to handle it; if the `CompletableFuture` is cancelled, you must define who is responsible for closing/cancelling the channel and handling the pending buffer. Therefore, adding a wrapper does not by itself solve lifecycle management.

## 12. Real-World Scenarios and Common Mistakes

### 12.1. “I’m already using AsynchronousSocketChannel, why is the server still slow?”

It may be because the code calls `read(...).get()` right inside the thread serving each connection; the thread still sits waiting for bytes to arrive. Consider separating I/O management into callbacks, pipelines, appropriate workers, or using a thread model suited to your scale. Inspect thread dumps and the count of waiting threads before concluding the async API is at fault.

### 12.2. “The `completed` callback ran, why was only part of the response sent?”

The `Integer` in the write callback is **the number of bytes completed in that turn**, not guaranteed to equal the entire response. Check `buffer.hasRemaining()` and initiate the next write after completion until all data is sent. If the peer closes or resets, the result may be an error. Do not modify the buffer while a write is still pending.

### 12.3. “`Future.get` timed out, can I reuse the `ByteBuffer` for something else?”

You should not while the old operation is still pending. A `get` timeout does not cancel I/O; the channel may still write into the buffer after `get` expires. You must resolve the old operation or close the channel/reclaim the memory according to policy. With a channel I/O timeout, the buffer state is even more dangerous because the Javadoc says it is undefined.

### 12.4. “The callback received `-1`; should Java have called `failed`?”

No. `completed(-1, attachment)` indicates that the TCP read completed and encountered EOF. That is not an I/O error; the right action is to terminate/half-close the protocol and release appropriate resources. `failed(Throwable,...)` reports that the operation failed.

### 12.5. “Can I start multiple asynchronous reads from different threads?”

No, if on the **same `AsynchronousSocketChannel`** there is still a pending read; per Javadoc it will throw `ReadPendingException`. Likewise `WritePendingException`. One read and one write can be pending at the same time, but you must protect message ordering and shared data.

### 12.6. “Which thread does `CompletionHandler` run on?”

Callbacks are usually dispatched according to the mechanism of the asynchronous channel group/provider. You must not write code that depends on the callback always running on the caller thread, nor assume callbacks only run on a single thread. Shared state needs proper synchronization, such as `AtomicReference`/`ConcurrentHashMap` or an actor/serial-executor design. Long, blocking callbacks can tie up threads serving completions for the group.

### 12.7. “The callback failed, why doesn’t the main thread see the exception?”

If an exception occurs in a callback, it is not automatically rethrown up the stack of the thread that previously called `read(...)`. Report errors through an explicit mechanism (handler error path, promise, state machine, queue), log context, and perform cleanup. In the demo, `AtomicReference<Throwable>` and `CountDownLatch` pass the error result back to `main` solely for testing.

### 12.8. “The server accepts once and then stops accepting new clients?”

With an accept callback, when a connection is accepted successfully you must **initiate the next accept** if you want to keep serving. Only one accept outstanding is allowed, so re-register inside `completed`. With a Future loop, only call the next accept after receiving the previous accept result and handing off the accepted socket for management.

### 12.9. “Can closing a channel complete a callback with an error?”

Yes. A pending operation can terminate with failure when the channel is closed, and the `failed` callback must handle it without turning a normal shutdown into an infinite retry loop. Apply a state machine to idempotently close each connection and avoid updating an already finished session.

## 13. Designing an Asynchronous Server with Limits and Backpressure

A real server does not just need to receive results; it also needs to remain safe under thousands of connections:

1. **Ownership:** each connection owns its socket, read buffer, write queue, and protocol state clearly. Never have two reads or two writes outstanding on one channel.
2. **Framing:** limit header/body sizes, decode by length prefix/delimiter, and protect against clients sending data extremely slowly.
3. **Deadline:** timeout per I/O and overall request/session; when expired, deterministically close/cancel instead of letting a Future or callback wait forever.
4. **Backpressure:** if a client reads slowly, cap the bytes queued for sending; do not allocate endlessly and call `write()` asynchronously without bounds.
5. **Threading:** keep callbacks short; offload long CPU/DB/blocking tasks to another bounded executor. Configure `AsynchronousChannelGroup` if you need control over threads and lifecycle.
6. **Failure handling:** handle synchronous operation initiation errors, asynchronous Future/callback errors, EOF, cancellation, and shutdown.
7. **Resource cleanup:** close sockets/listeners, cancel pending operations appropriately, release buffers/pools, and complete requests **once** even when multiple error paths race.
8. **Observability:** log request ID/peer/operation, pending reads/writes, bytesRead/bytesWritten, latency, timeouts, and number of live connections; avoid logging sensitive payload information.
9. **Do not conflate transport and business logic:** the number of bytes written on local TCP does not prove the peer application has processed them; require protocol-level ACK/response when needed.
10. **Failure testing:** besides normal loopback, test unexpected peer close, partial frames, timeouts, slow networks, callback failures, concurrent channel close, overload, and mid-stream connection drops.

When handling thousands of connections, callbacks do not automatically reduce the number of sockets, file descriptors, buffer memory, or CPU needed for payloads. The success of the model depends on admission control, bounded queues, deadlines, and state machines.

## 14. Self-Check Questions

**Question 1.** `Future<Integer> f = channel.read(buf)` has returned. Is `buf` guaranteed to already contain data ready to read?  
**Answer:** No. The I/O may not have completed yet; you must wait on the Future or check the completion result properly. Do not modify buffer positions while pending.

**Question 2.** `f.get(2, SECONDS)` throws `TimeoutException`. Has the read operation been cancelled?  
**Answer:** Not guaranteed. The timeout only applies to how long the thread waits on the Future; the operation may continue. Explicit lifecycle/cancel/close handling is needed.

**Question 3.** With `CompletionHandler<Integer, String>`, what does `String` mean?  
**Answer:** It is the attachment type: a request ID, correlation ID, or context passed by your code when initiating I/O; it is not byte content automatically extracted from the socket.

**Question 4.** Why is `completed(-1, attachment)` not handled the same way as `failed(...)`?  
**Answer:** `-1` is EOF of the TCP stream, which is a successful read result in terms of the API. `failed` receives a `Throwable` due to an I/O error.

**Question 5.** Why does `completed(writeCount)` need to check `src.hasRemaining()`?  
**Answer:** Asynchronous TCP writes can complete only part of the data. If the buffer still has remaining bytes, you must continue writing after completion according to the protocol.

**Question 6.** Can you call `channel.read(...)` twice in a row without waiting for the first one to finish?  
**Answer:** No. If the first one is still pending, the second call throws `ReadPendingException`. You can have one read and one write at the same time.

**Question 7.** What is the difference between `CompletionHandler` and `CompletableFuture`?  
**Answer:** One is an NIO.2-specific callback interface with an attachment; the other is a `Future`/`CompletionStage` class for chaining. You can wrap a handler with `CompletableFuture`, but the wrapper does not automatically handle cancellation and buffer ownership.

**Question 8.** How is an I/O timeout callback reported, and why must you be careful with the buffer?  
**Answer:** Channel timeout overloads may invoke `failed(InterruptedByTimeoutException, attachment)`. The Javadoc warns that the channel/connection may be inconsistent and the buffer state of a timed-out operation is undefined.

**Question 9.** If you want to asynchronously accept multiple clients in succession using `CompletionHandler`, when do you register the next accept?  
**Answer:** When the previous accept completes, typically right inside `completed`. Do not leave two accepts pending on the same listener because of `AcceptPendingException`.

**Question 10.** Why should you not run long DB processing directly inside `completed`?  
**Answer:** Callbacks may use the group's dispatch threads; long blocking work stalls other callbacks. Offload heavy work to a bounded executor and design backpressure.

## Java SE 17 Standard Documentation

- `AsynchronousSocketChannel` — connect/read/write, `Future`, handlers, timeouts, read/write pending: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html
- `AsynchronousServerSocketChannel` — accept via Future and handler, `AcceptPendingException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html
- `CompletionHandler<V,A>` — `completed` and `failed`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html
- `AsynchronousChannelGroup` — thread/channel group used for async I/O: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html
- `AsynchronousFileChannel` — Future/CompletionHandler with file position: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html
- `ByteBuffer` — position/limit/flip/clear: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- `Future` — get, timeout, cancellation, and state: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- `CompletableFuture` — a different API from `CompletionHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
