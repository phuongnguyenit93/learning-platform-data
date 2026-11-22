# One Pending Read and One Pending Write: Concurrency Limits in Java AsynchronousSocketChannel

In Java NIO.2, **`AsynchronousSocketChannel` supports one read operation and one write operation running concurrently on the same TCP channel**, but **at any given time there can be at most one pending read operation and at most one pending write operation**. If the application starts a new `read` before the previous `read` has completed, Java throws **`ReadPendingException`**. Similarly, starting a new `write` before the previous `write` has completed throws **`WritePendingException`**.

This is a limit on **outstanding I/O operations**, not a limit of "one thread" or "one request for the entire server". The same channel can have both a pending read and a pending write; different channels have independent limits. This article belongs to the **Asynchronous I/O** topic and explains the exact semantics, how to manage `Future`/`CompletionHandler`, `ByteBuffer`, and queues so that errors do not occur when multiple tasks send/receive concurrently.

The final two examples are **complete Java 17+ programs**, running on `127.0.0.1` with dynamic ports, requiring no Internet or external server.

## 1. What does "pending" (outstanding) actually mean?

A call to:

~~~java
Future<Integer> readResult = channel.read(readBuffer);
~~~

**initiates** an asynchronous read operation. Returning a `Future` does **not** mean the bytes have finished being read. The I/O provider may be waiting for data or processing completion. From the moment the operation is accepted until it **completes/fails**, it occupies the channel's **read slot**.

Similarly:

~~~java
Future<Integer> writeResult = channel.write(writeBuffer);
~~~

occupies the **write slot** while the write is outstanding. Once the operation completes, the application can continue initiating another operation of the same type (if the channel is still in a valid state).

Mental model:

~~~text
A connected AsynchronousSocketChannel
┌───────────────────────────────────────────────────────────┐
│ Read slot:   [FREE] -- read() --> [PENDING] --> [FREE]     │
│                           |                               │
│                           +-- 2nd read() ----> EXCEPTION   │
│                                                           │
│ Write slot:  [FREE] -- write() -> [PENDING] --> [FREE]     │
│                           |                               │
│                           +-- 2nd write() ---> EXCEPTION   │
└───────────────────────────────────────────────────────────┘

Read pending + Write pending on the SAME channel: ALLOWED.
Two reads pending on the SAME channel: NOT ALLOWED.
Two writes pending on the SAME channel: NOT ALLOWED.
~~~

The `FREE/PENDING` labels are an illustrative model, not an enum in the Java API. Calling `read` once and then calling `read` **immediately afterward** does not automatically create a "read queue" inside the channel. If the previous read is still pending, the API throws an exception on the next call.

**Do not infer that "each connection is only allowed one I/O operation in total".** The limit is **one read plus one write**; the two directions of full-duplex TCP can progress independently.

## 2. Concurrent operation matrix: what is valid?

| Current state of the same channel | New operation | Result per API contract |
| --- | --- | --- |
| No read pending | `read(buffer)` | Can initiate read |
| Read already pending | Additional `read(otherBuffer)` | `ReadPendingException` |
| Read already pending | `write(buffer)` when no write is pending | **Allowed**, read and write can overlap |
| No write pending | `write(buffer)` | Can initiate write |
| Write already pending | Additional `write(otherBuffer)` | `WritePendingException` |
| Write already pending | `read(buffer)` when no read is pending | **Allowed** |
| Read on channel A and read on channel B | Both pending simultaneously | **Allowed**: two channels have separate states |
| One read + one write pending on channel A | Additional read on channel B | Allowed, if channel B is valid |

Important: `ReadPendingException` or `WritePendingException` only occurs **when the previous operation has genuinely not completed**. A small `write` to a socket with an empty kernel buffer can complete extremely fast; calling it twice in a row **does not guarantee** the second call throws `WritePendingException`. Do not write unit tests that rely on the socket being slow. To test coordination logic, use controllable state/queues or a reliably pending situation (such as a read with no data available yet).

This limit belongs to **`AsynchronousSocketChannel`**; do not generalize that every Java async I/O class has exactly one read and one write. For example, `AsynchronousFileChannel` has operations by file position and its own concurrency rules. Check the contract of **each channel type**.

## 3. Related APIs: Future and CompletionHandler

Java has two ways to initiate async operations on `AsynchronousSocketChannel`:

### 3.1. Future: retrieving the result later

~~~java
Future<Integer> readFuture = channel.read(dst);
Future<Integer> writeFuture = channel.write(src);

// Other work can be done here, or wait if the program requires it.
int bytesRead = readFuture.get();
int bytesWritten = writeFuture.get();
~~~

This is a **snippet** inside a method that already has a connected channel, buffers, and imports. `Future.get()` **blocks the thread calling get** until completion; `channel.read(dst)` itself is the call that initiates async I/O.

- For `read`, a result `n > 0` is the number of bytes received; `0` can occur with a buffer that has no remaining space or depending on operation conditions; `-1` signals **end-of-stream/EOF**.
- For `write`, the result is the number of bytes transferred from the buffer to the socket, which may be **fewer than the number of bytes needing to be sent**. Completion does not prove the peer has read the data.
- `get()` can throw `ExecutionException` (the real cause is in `getCause()`) or `InterruptedException`; `get(timeout, unit)` can also throw `TimeoutException` when **the caller's wait for the result** exceeds the timeout.
- A `Future` can complete very quickly before the code even calls `get()`. This does not change the rule: at most one **outstanding** operation per I/O direction.

Note: if you use `Future.get(1, SECONDS)` and receive `TimeoutException`, **do not conclude that the I/O has stopped**. This is a timeout of *waiting for the Future*, not necessarily a timeout of the operation itself. The operation may still be pending; initiating a read/write of the same type right after the timeout can cause a pending exception.

### 3.2. CompletionHandler: success or failure notifications

When using callbacks:

~~~java
channel.read(dst, dst, new CompletionHandler<Integer, ByteBuffer>() {
    @Override
    public void completed(Integer count, ByteBuffer buffer) {
        // Read operation completed: check count, process bytes.
    }

    @Override
    public void failed(Throwable error, ByteBuffer buffer) {
        // Read operation failed: log error, close channel/cleanup.
    }
});
~~~

This is a **snippet**, requiring `import java.nio.channels.CompletionHandler;`, `ByteBuffer`, and a valid `channel` variable. The attachment parameter (here `dst`) is passed back to the handler to link the operation with the request/connection state.

There are also overloads with a timeout, for example:

~~~java
channel.read(
    dst, 2, TimeUnit.SECONDS, attachment, handler);
channel.write(
    src, 2, TimeUnit.SECONDS, attachment, handler);
~~~

This is a snippet; `attachment`, `handler`, and `TimeUnit` are declared at the call site. These overloads specify an **I/O timeout**: if it does not complete within the deadline, the handler may be invoked via the `failed` branch with `InterruptedByTimeoutException`. The important difference from `Future.get(timeout)` will be explained in the timeout section.

**Pending exceptions occur when starting a new operation**, rather than being "read errors delivered to the callback" in the sense of always calling `failed`. For example, calling `read(...)` while a read is still outstanding can throw `ReadPendingException` **directly on the calling thread**; the application must manage serializing operations itself before submitting them to the provider.

## 4. API contract: thread-safe channel ≠ unlimited concurrent operations

The Javadoc explicitly states that `AsynchronousSocketChannel` is **safe for use by multiple concurrent threads**, while also allowing at most one read and one write outstanding. These two statements do not contradict each other.

- **Thread-safe channel:** Multiple threads can reference the same channel and invoke appropriate methods without corrupting the channel's internal state.
- **Operation concurrency limit:** Two threads calling `read` concurrently on the **same channel** can hit the pending limit; one operation may be rejected with `ReadPendingException`.
- **Buffer ownership:** `ByteBuffer` is **not thread-safe** in the sense of allowing multiple threads to arbitrarily modify `position/limit/content` at the same time. While I/O is outstanding, do not modify that buffer on another thread; wait for completion before reading/modifying/reusing it.
- **Completion callbacks:** Do not assume callbacks always run on the same thread that initiated them or in the order of all operations. When callbacks and business logic both modify connection state, use an explicit coordination/synchronization mechanism.

**Practical rule:** Let a single connection manager (actor, event loop, or synchronized per-connection state) own the "read slot", "write slot", input/output buffers, and output queue. That prevents two different handlers from accidentally calling `write` on the same channel at the same time.

## 5. Complete example: detecting pending read and reading while writing

The following program uses **three asynchronous channels**: one `AsynchronousServerSocketChannel` for listening and two `AsynchronousSocketChannel` instances representing the two ends of a local TCP connection. This structure enables a controlled test:

1. Server binds to `127.0.0.1:0`, and the OS assigns a dynamic port.
2. Server calls `accept()`, client calls `connect()` and waits for the connection to succeed.
3. Client starts `read(response)` **before the server sends anything**: one pending read.
4. Client calls read a second time and catches `ReadPendingException`; this is a deterministic check because the server has not sent a response yet.
5. **While the client's read is pending**, the client itself calls `write("ping")`: this is the allowed case.
6. Server receives all 4 bytes and sends `"pong"`; client reads the full response. All I/O waits use `get(3, SECONDS)` so the demo does not block indefinitely.

Create the file **`OneReadOneWriteDemo.java`** (UTF-8):

~~~java
import java.io.EOFException;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.ReadPendingException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class OneReadOneWriteDemo {
    private static void writeAll(
            AsynchronousSocketChannel ch, ByteBuffer src) throws Exception {
        while (src.hasRemaining()) {
            int n = ch.write(src).get(3, TimeUnit.SECONDS);
            if (n < 0) {
                throw new EOFException("Write channel closed");
            }
        }
    }

    private static ByteBuffer readExactly(
            AsynchronousSocketChannel ch, int bytes) throws Exception {
        ByteBuffer dst = ByteBuffer.allocate(bytes);
        while (dst.hasRemaining()) {
            int n = ch.read(dst).get(3, TimeUnit.SECONDS);
            if (n < 0) {
                throw new EOFException("Premature EOF");
            }
        }
        dst.flip();
        return dst;
    }

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            InetSocketAddress address =
                    (InetSocketAddress) listener.getLocalAddress();

            Future<AsynchronousSocketChannel> accepting = listener.accept();
            client.connect(address).get(3, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel server =
                         accepting.get(3, TimeUnit.SECONDS)) {

                ByteBuffer response = ByteBuffer.allocate(4);

                // Nobody has sent data to the client yet: read stays pending.
                Future<Integer> pendingRead = client.read(response);
                boolean rejectedSecondRead = false;

                try {
                    client.read(ByteBuffer.allocate(4));
                } catch (ReadPendingException expected) {
                    rejectedSecondRead = true;
                }

                if (!rejectedSecondRead) {
                    throw new AssertionError("Expected ReadPendingException");
                }

                // Client can WRITE while its own read is pending.
                writeAll(client, StandardCharsets.UTF_8.encode("ping"));

                String serverReceived = StandardCharsets.UTF_8.decode(
                        readExactly(server, 4)).toString();

                writeAll(server, StandardCharsets.UTF_8.encode("pong"));

                int first = pendingRead.get(3, TimeUnit.SECONDS);
                if (first < 0) {
                    throw new EOFException("No response");
                }
                while (response.position() < 4) {
                    int n = client.read(response).get(3, TimeUnit.SECONDS);
                    if (n < 0) {
                        throw new EOFException("Truncated response");
                    }
                }
                response.flip();

                System.out.println("Second read rejected: "
                        + rejectedSecondRead);
                System.out.println("Server received: " + serverReceived);
                System.out.println("Client received: "
                        + StandardCharsets.UTF_8.decode(response));
                System.out.println("Read and write overlapped: true");
            }
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 OneReadOneWriteDemo.java
java OneReadOneWriteDemo
~~~

**Stdout on a normal TCP loopback environment:**

~~~text
Second read rejected: true
Server received: ping
Client received: pong
Read and write overlapped: true
~~~

Detailed breakdown:

- `listener.accept()` and `client.connect(...)` are started asynchronously; their results are retrieved with `Future.get()` to keep the demo code short and clearly ordered.
- `pendingRead` occupies the **client's read slot**. Because the server has not sent data yet, the read cannot complete. Therefore, attempting a second `client.read(ByteBuffer.allocate(4))` is rejected with `ReadPendingException`.
- `writeAll(client, "ping")` uses the **write direction**, which is still allowed even while the client's read is pending. This is precisely what full-duplex TCP on a single `AsynchronousSocketChannel` means.
- `writeAll` loops while `src.hasRemaining()` to handle **partial writes**. It always waits for the previous write to complete before initiating the next write; it never creates two pending writes.
- `readExactly` reads until the exact number of required bytes arrives, always waiting for the previous read to complete before starting the next read. TCP is a byte stream; 4 bytes may arrive across multiple completions.
- After `pendingRead.get(...)` returns, the previous read has finished. If only part of `"pong"` was read, the code then calls `client.read(...)` again. At that point there is no outstanding read, so it is valid.
- The program does not intentionally try to trigger two pending writes, because a small write can complete too quickly to reproduce that error reliably.
- A `get(timeout)` expiration will throw an exception and the try-with-resources block will close the channels. This example should not be taken as a production protocol handling every network failure.

## 6. Why "calling write twice in a row" is not a reliable unit test

Consider the code:

~~~java
Future<Integer> first = channel.write(bufferA);
Future<Integer> second = channel.write(bufferB);
~~~

On a fast-writing TCP connection, `first` may **already have completed** before the second call happens. In that case the two writes do not overlap, so the second call **may be valid**. Conversely, if `first` is still pending, the second write call throws `WritePendingException`.

Therefore:
- Do not assert that this code **always** throws an exception.
- Do not assume this code is **always** safe just because it passes on a fast test machine.
- Do not use `Thread.sleep(10)` to "synchronize" two writes; timing depends on the OS, CPU, socket buffer, scheduler, and payload size.
- Do not let the exception occur and retry in a busy loop. A pending exception is a **signal that the application violated submission ordering**, not an effective way to throttle network traffic.

If multiple producers have data to send, have each producer **enqueue** into a bounded output queue. A single writer logic owns the right to call `channel.write(...)` per channel and only submits the next write once the previous one **completes**.

## 7. How to serialize writes: only one writer operation, yet many messages

A simple model for one connection:

~~~text
Producer A ----\
Producer B -----+--> per-connection output queue
Producer C ----/                 |
                                  v
                          writer state machine
                                  |
                         [no write pending?]
                           /             \
                         YES             NO
                          |               |
                          v               v
                     poll buffer      keep in queue
                          |
                      channel.write()
                          |
                         pending
                          |
                 completed/failed callback
                          |
                buffer.hasRemaining() ?
                  /               \
                YES               NO
                 |                 |
          write remaining      take next buffer
          bytes (after         if queue is not
          completion)          empty
~~~

**Invariants** to maintain:

1. **One in-flight write** per channel; other messages stay in the application's queue instead of calling `channel.write` in parallel.
2. A buffer currently being written **is not modified by producers**. Producers only transfer ownership of the buffer into the queue after preparing it (e.g., `flip()`).
3. When the write callback finishes, if the buffer still has remaining bytes, submit a new write for the **same buffer** after the previous operation has completed.
4. Only when the current buffer has no remaining bytes, take the next buffer from the queue.
5. If the queue/pending bytes exceed a threshold, pause producers or reject requests. Do not let the queue grow unbounded because of a slow-reading client.
6. If an exception occurs or the channel closes, **stop sending further data** and complete/cancel application promises according to the defined policy.

Example **snippet inside a callback method that already has connection state**, not a standalone program:

~~~java
private void writeNext(ByteBuffer pending) {
    channel.write(pending, pending,
            new CompletionHandler<Integer, ByteBuffer>() {
        @Override
        public void completed(Integer n, ByteBuffer buffer) {
            if (buffer.hasRemaining()) {
                // Previous write HAS completed: now allowed to call the next write.
                writeNext(buffer);
            } else {
                // Take the next buffer from the output queue if available.
                drainNextQueuedBuffer();
            }
        }

        @Override
        public void failed(Throwable exc, ByteBuffer buffer) {
            failAndCloseConnection(exc);
        }
    });
}
~~~

This snippet **assumes** `channel`, `drainNextQueuedBuffer()`, and `failAndCloseConnection()` are members of the connection-state owner and that the queue is synchronized; method names illustrate the flow and are not standard Java APIs. When an application uses callbacks that can run on multiple threads, the transition from "writing" to "taking the next queue element" must be **serialized/synchronized**; simply having a thread-safe queue is not enough if two producers both see `writing == false` and both call `write`.

Some implementation approaches:
- A per-connection event loop/actor receives enqueue commands and only the event-loop thread calls write.
- A short lock protecting `writingFlag` and the queue, avoiding holding the lock while I/O is waiting.
- A state machine using an atomic flag and a bounded queue, with state transitions verified against lost wakeups.

This is coordination at the **application layer** to obey the channel's limit, rather than an automatic write-queuing mechanism built into `AsynchronousSocketChannel`.

## 8. CompletionHandler: scheduling the next read after the current one completes

For a server reading a stream multiple times, the principle is to **chain reads** inside completion rather than calling them back-to-back before getting a result. For a protocol with a known length, the handler needs to handle both partial reads and EOF.

The program below uses a callback to receive exactly 4 bytes. Each time `completed` receives data but the buffer is not yet full, the handler **reschedules a read**. The callback only submits the next read after the previous one completes, so it never violates the pending limit.

Create the file **`CallbackReadDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CallbackReadDemo {
    static void writeAll(AsynchronousSocketChannel ch, ByteBuffer data)
            throws Exception {
        while (data.hasRemaining()) {
            if (ch.write(data).get(3, TimeUnit.SECONDS) < 0) {
                throw new EOFException("Write failed");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            Future<AsynchronousSocketChannel> accepting = listener.accept();
            client.connect(listener.getLocalAddress())
                    .get(3, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel server =
                         accepting.get(3, TimeUnit.SECONDS)) {

                CountDownLatch done = new CountDownLatch(1);
                AtomicReference<String> received = new AtomicReference<>();
                AtomicReference<Throwable> error = new AtomicReference<>();
                ByteBuffer buffer = ByteBuffer.allocate(4);

                CompletionHandler<Integer, ByteBuffer> handler =
                        new CompletionHandler<>() {
                    @Override
                    public void completed(Integer n, ByteBuffer dst) {
                        if (n == -1) {
                            failed(new EOFException("Early EOF"), dst);
                        } else if (dst.hasRemaining()) {
                            server.read(dst, dst, this);
                        } else {
                            dst.flip();
                            received.set(
                                    StandardCharsets.UTF_8.decode(dst)
                                            .toString());
                            done.countDown();
                        }
                    }

                    @Override
                    public void failed(Throwable cause, ByteBuffer dst) {
                        error.set(cause);
                        done.countDown();
                    }
                };

                server.read(buffer, buffer, handler);
                writeAll(client, StandardCharsets.UTF_8.encode("ping"));

                if (!done.await(3, TimeUnit.SECONDS)) {
                    throw new IOException("Timed out waiting for callback");
                }
                if (error.get() != null) {
                    throw new IOException("Read failed", error.get());
                }

                System.out.println("Callback received: " + received.get());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CallbackReadDemo.java
java CallbackReadDemo
~~~

**Stdout if TCP loopback works:**

~~~text
Callback received: ping
~~~

To let the demo terminate on its own, `CountDownLatch` is only used in **main** to wait for the handler; the handler itself does not call `Future.get()` and does not block waiting for another I/O. `AtomicReference` stores the result/error for the main thread, and `countDown()` signals completion.

For a real server, callbacks can be used to chain a continuous read/parse/write lifecycle, but framing, buffer limits, idle timeouts, error handling, and backpressure must be applied. The attachment parameter `dst` pairs the exact buffer with the read operation. Do not use that buffer on another thread while pending.

**Callback handler note:** Once the callback for the previous read is invoked, initiating the next read fits the chaining model; however, in an application where multiple producers/callbacks modify state, you must still own the buffers and serialize state transitions.

## 9. Partial read, partial write, and TCP framing

The limit of one pending operation **by no means** guarantees that one completion equals one application message.

**TCP carries a byte stream:**
- One `write(100 bytes)` on the client does not necessarily correspond to one `read(100 bytes)` on the server.
- One read may receive 1 byte, 100 bytes, or multiple messages concatenated together if the buffer is large enough.
- One write may complete with `n < initial src.remaining()`, even without any error.
- Reading `-1` means the peer has ended the input stream (EOF), not an empty application packet.
- A completed write means data has been transferred out of the application buffer per the socket I/O contract; **it does not prove the remote application has received and processed it**.

Therefore, two layers of organization are needed:

| Layer | Responsibility |
| --- | --- |
| I/O scheduling | Ensure ≤1 read pending, ≤1 write pending per channel |
| Protocol framing | Determine when a full message is complete, e.g., length-prefix, delimiter, fixed size; validate size and encoding |

For variable-length messages, a 4-byte length header in network byte order can be used:
1. Read until the **header** is complete; parse the size safely.
2. Check the length against the application limit before allocating a buffer.
3. Read until the payload is complete, possibly across multiple async read completions.
4. Decode/dispatch the message.
5. If new data is expected, continue reading according to the state machine.

Do not write a handler like:

~~~java
// WRONG if treating a single read completion as a complete request.
channel.read(buffer, null, new CompletionHandler<>() {
    @Override
    public void completed(Integer n, Object ignored) {
        processOneFullRequest(buffer); // No check yet whether a full frame arrived.
    }
    @Override
    public void failed(Throwable error, Object ignored) {
        closeConnection();
    }
});
~~~

This is **anti-pattern code**, not a complete program; `processOneFullRequest` and `closeConnection` only illustrate the design flaw. Parser state and `n`/EOF checks are needed before dispatching. If a UTF-8 code point is split across multiple reads, use a stateful decoder or decode only once a complete frame is available.

## 10. ByteBuffer ownership and concurrent data

Even with only one read and one write, a **data race** can still occur if both operations use the same `ByteBuffer`:

~~~java
// RISK: two I/O operations can modify the same buffer.position.
ByteBuffer shared = ByteBuffer.allocate(1024);
Future<Integer> reading = channel.read(shared);
Future<Integer> writing = channel.write(shared);
~~~

Channel read and write are **two valid directions**, but the `ByteBuffer` `shared` is a mutable object and is not safe when operated on by two I/O operations concurrently; `position` and bytes can change while the provider executes I/O.

Correct pattern for full-duplex:

~~~java
ByteBuffer inbound = ByteBuffer.allocate(8192);
ByteBuffer outbound = ByteBuffer.wrap(responseBytes);

Future<Integer> readFuture = channel.read(inbound);
Future<Integer> writeFuture = channel.write(outbound);
~~~

This is a snippet where `responseBytes` is a separate prepared byte array. Each operation owns its own buffer until completion. Even with separate arrays, **do not modify** the contents of `outbound` before the write completes, or read/modify `inbound` while the read has not completed.

When a read completes:
- With `n > 0`, the buffer position has advanced by `n`.
- Use `flip()` to switch to reading the received bytes; only do this **after completion**.
- When parsing does not consume all bytes, use `compact()` to preserve the remainder, and only submit a new read when the buffer is in write mode.
- Do not call `clear()` and overwrite data still needed by the parser or an in-flight write.
- Data can be copied into an immutable message before handing it off to CPU/DB workers.

For a pending write, keep the same `ByteBuffer` until completion; after the written portion finishes, `hasRemaining()` determines whether to write more or move on to another message.

## 11. Timeout: distinguishing Future wait timeout from I/O operation timeout

This distinction is especially important for the "pending" state:

| Mechanism | Example | When time expires | Impact on pending slot |
| --- | --- | --- | --- |
| **Future wait timeout** | `future.get(1, SECONDS)` | Waiting thread receives `TimeoutException` | **Does not automatically terminate** I/O; operation may remain pending |
| **I/O timeout in callback overload** | `channel.read(dst, 1, SECONDS, state, handler)` | Operation completes as failed via `InterruptedByTimeoutException` | May leave channel/data in an error state determined by the provider |
| **Close channel** | `channel.close()` | Ends channel lifecycle; pending I/O is failed/cancelled per contract and provider | Do not continue using the closed channel |

A common mistake:

~~~java
Future<Integer> first = channel.read(dst);
try {
    first.get(1, TimeUnit.SECONDS);
} catch (TimeoutException e) {
    // WRONG: first may still be pending; next read will throw ReadPendingException.
    channel.read(otherDst);
}
~~~

This is an **anti-pattern snippet** (requiring full declarations/imports), not a recommended approach.

If you cannot wait any longer, define a **lifecycle policy**: you can close the connection to release resources and open another channel when needed; do not initiate the same operation on a channel whose pending state is not known to be clear. When an application uses `Future.cancel(...)`, do not rely solely on the Future's cancelled state to assume the byte buffer or channel state transition is always safe; follow the channel and provider contract and close the connection when the state is uncertain.

**Warning about real I/O timeouts:** The `AsynchronousSocketChannel` Javadoc states that a timeout may leave the channel or underlying connection in an inconsistent state. When the provider cannot guarantee whether data was or was not transferred, subsequent reads/writes may be rejected with an unspecified runtime exception; the state of the `ByteBuffer` after an I/O timeout may be **undefined**. For protocols requiring correctness, it is usually best to **close the connection and discard the associated buffers** rather than retrying on the same channel as if nothing happened.

With timeout overloads, a timeout value **≤0** is interpreted by the Java API as no timeout for the I/O operation, which is completely different from `Future.get(0, unit)` meaning "wait at most 0 time units" at the Future level.

## 12. Cancellation, close, and error handling

Common errors in async code:

| Exception / state | Meaning | Strategy |
| --- | --- | --- |
| `ReadPendingException` | A read is already outstanding on the channel | Do not submit another; wait for completion, fix read state |
| `WritePendingException` | A write is already outstanding on the channel | Enqueue output, serialize writes per connection |
| `NotYetConnectedException` | Read/write called before the TCP channel finished connecting | Wait for connect Future/callback to complete |
| `ConnectionPendingException` | New connect called while previous connect is still pending | Only one connect flow per channel |
| `InterruptedByTimeoutException` | I/O callback operation exceeded timeout | Discard suspect buffer, close/recreate channel per policy |
| `AsynchronousCloseException` / `ClosedChannelException` | Channel closed during operation or before initiation | Clean up state and stop submitting |
| `ExecutionException` from `Future.get()` | I/O future completed with failure | Inspect `getCause()`, handle underlying error |
| `TimeoutException` from `Future.get(timeout)` | Caller waited too long | Operation may still be pending; do not submit duplicate |
| `CancellationException` | Future was cancelled | Do not assume data transfer or buffer was rolled back |
| `n == -1` on read | EOF, remote peer ended input stream | Handle shutdown/half-close/close per protocol |

**Closing the channel** in `try-with-resources` or explicit cleanup is a clear way to end the lifecycle. In a real system, when a connection breaks, you should:
1. Mark the state as CLOSED.
2. Stop accepting new read/write requests for that channel.
3. Close the channel.
4. Complete any waiting business futures/promises or callbacks with a contextual error.
5. Clear/release the output queue and buffers only when no I/O is writing to them anymore; if the provider reports an undefined buffer state after a timeout, do not reuse them arbitrarily.

**Do not swallow a pending exception and immediately retry in a while loop**. If an event handler repeatedly encounters `WritePendingException`, the bug is in **scheduling/state machine**, not necessarily network overload.

## 13. Do not confuse with AsynchronousServerSocketChannel and AsynchronousFileChannel

Although all their names start with "Asynchronous", each API has its own limits:

- `AsynchronousSocketChannel`: one pending read and one pending write, **both directions can overlap**.
- `AsynchronousServerSocketChannel`: uses `accept()` to accept connections; a pending accept is not the same as read/write on a client channel. This class also limits to **one pending accept** and has `AcceptPendingException` if a new accept is started before the previous one completes.
- `AsynchronousFileChannel`: read/write operations at specific file positions, not simply governed by the same socket pending limit here; consult the class Javadoc when designing concurrency.
- `SocketChannel` in non-blocking NIO uses `Selector` and readiness for coordination; `AsynchronousSocketChannel` uses Future/callback completion. Both models can handle many connections, but **do not use the same API**.
- `AsynchronousChannelGroup` manages execution resources for callbacks/member channels; **it does not increase the number of pending reads/writes for a single socket**. The number of worker threads in the group is not the number of outstanding I/O operations per channel.

This helps choose the right tool:
- Need to know when a socket is **ready** to perform I/O → look into `Selector`.
- Need to initiate I/O and receive **completion** via `Future`/`CompletionHandler` → use `AsynchronousSocketChannel`.
- Need to handle multiple concurrent writes on one connection → use an **output queue and a single writer state machine**, rather than adding more threads to "force" the channel to accept multiple outstanding writes.

## 14. Operating on a server with many connections

An asynchronous server serving many clients should manage **per-connection state**:

~~~text
acceptor
   |
   +--> client A  [readPending?] [writePending?] [output queue]
   |
   +--> client B  [readPending?] [writePending?] [output queue]
   |
   +--> client C  [readPending?] [writePending?] [output queue]
   |
   +--> ...

Each client can have:
   - at most 1 read pending
   - at most 1 write pending
   - multiple messages QUEUED at the application layer (bounded)
~~~

For efficiency and correctness:
- Clearly own operation state and buffers per connection.
- Have the read callback re-arm only when more data is desired and when there is capacity/backpressure headroom.
- Have the write callback drain the queue in protocol order and only submit the next write after completion.
- Use a bounded queue and high/low-water marks; stop accepting input or reject requests when output producers outpace the peer's reading.
- When CPU work or blocking database calls are long-running, offload them to a bounded executor; do **not** block callback threads that serve many channels.
- When the response is finished, handle half-close, flush, and close in the proper order; do not drop pending data.
- Set timeouts and policies for idle connections, and isolate errors per connection instead of crashing the entire server.
- Log the number of pending reads/writes, queue depth, and byte counts to diagnose slow clients or memory pressure.

If a server has 1000 `AsynchronousSocketChannel` instances, it does not mean only one read is allowed for the entire server: each channel can independently have one pending read and one pending write. Nor does it mean 1000 operations complete instantaneously; throughput depends on the scheduler, executor/group, OS, network, and peer speed.

## 15. Common design mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `read` twice before the first finishes | `ReadPendingException` | Track read-in-flight, only re-arm after completion |
| Calling `write` from two producers simultaneously | `WritePendingException` when writes overlap | Output queue + single writer logic |
| Thinking pending read forbids write | Wastes TCP's full-duplex capability | Allow one read and one write to coexist using separate buffers |
| Thinking every write call stays pending long enough | Flaky tests; bug only surfaces on slow networks | Test scheduling/state instead of timing |
| Sharing one `ByteBuffer` for read and write | Race on position/bytes | Separate buffers and ownership |
| Calling `flip()/clear()` before I/O completes | Corrupted or lost data | Only manipulate buffer after completion |
| Assuming one Future completion is one full message | TCP has partial I/O | Accumulate complete frames per protocol |
| Treating `Future.get(timeout)` as cancelling I/O | Read/write may still be pending | Define clear timeout/close policy |
| Retrying on the channel after an async I/O timeout as normal | Buffer/connection may be inconsistent | Close/recreate, do not reuse suspect data |
| Not handling EOF `-1` | Infinite reads / delayed close | Handle half-close and lifecycle |
| Unbounded output queue | Slow clients can cause OOM | Backpressure / bounded queue size |
| Waiting on `Future.get()` in every callback | Can block completion threads | Chain callbacks or offload logic |
| Assuming callbacks always run on one thread | Races on connection state | Serialize state transitions |
| Calling read/write before connected | `NotYetConnectedException` | Only perform I/O after connect completes |
| Thinking more threads in AsyncChannelGroup allows two writes | Violates API contract | Only one pending writer regardless of thread count |

## 16. Self-check exercises

**1.** A channel has a pending `read()`; can `write()` be called immediately?  
**Answer:** Yes, if no other write is outstanding and the channel is valid. One read and one write are allowed to overlap.

**2.** If two threads call `read()` concurrently on the same `AsynchronousSocketChannel`, what happens?  
**Answer:** Two reads cannot be outstanding; one call may throw `ReadPendingException` if the other read has not completed yet.

**3.** Is it valid for two channels A and B to both have a pending read at the same time?  
**Answer:** Yes. The limit applies **per channel**, not across the entire JVM or AsyncChannelGroup.

**4.** Why does a second `write()` call sometimes not throw `WritePendingException`?  
**Answer:** The first write may have completed before the second call. The exception only occurs if the writes actually overlap.

**5.** Does `Future.get(1, SECONDS)` throwing `TimeoutException` mean the read operation timed out and the slot is free?  
**Answer:** No. The caller timed out waiting, but the operation may still be outstanding.

**6.** Should you modify `ByteBuffer.position()` while an async read is pending?  
**Answer:** No. The buffer belongs to the I/O operation until completion.

**7.** Does `writeFuture.get() == 4` prove the peer has processed 4 bytes?  
**Answer:** No. It is only the result of the local channel's write operation; receiving/processing at the peer is a separate layer.

**8.** A callback receives 2 of 4 bytes of a frame; what should it do next?  
**Answer:** Keep the buffer/parser state, re-arm a read **after the previous read completes**, and continue until the full frame arrives or EOF/error occurs.

**9.** If a server has 100 channels, what is the maximum number of pending reads under this contract?  
**Answer:** At most one pending read **per** channel, so under the per-channel limit there can be up to 100 outstanding reads; actual resource limits also depend on the provider/OS.

**10.** When needing to send ten messages on the same connection while only one write can be pending, what design is appropriate?  
**Answer:** A bounded output queue with a single writer state machine, handling partial writes and submitting the next buffer after completion.

## Official references

- [Java SE 17 — AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): limit of at most one outstanding read and one outstanding write, Future/CompletionHandler, timeout, exception types.
- [Java SE 17 — AsynchronousByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html): read/write semantics, ByteBuffer ownership, and Future methods.
- [Java SE 17 — ReadPendingException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ReadPendingException.html) and [WritePendingException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/WritePendingException.html): thrown when an operation of the same type is already outstanding.
- [Java SE 17 — CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): completion/failure callbacks.
- [Java SE 17 — AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): pending accept and server-side lifecycle.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): position/limit/flip/compact, data ownership boundaries.
