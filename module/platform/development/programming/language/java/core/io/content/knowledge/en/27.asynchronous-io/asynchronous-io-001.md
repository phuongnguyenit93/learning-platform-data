# Distinguishing Asynchronous I/O from Non-blocking I/O in Java

## 1. Objectives and Context

When designing efficient I/O programs, the two terms **asynchronous I/O** and **non-blocking I/O** are often used interchangeably. They are related, but **not synonymous**.

- **Non-blocking** describes the behavior of a **specific I/O call**: when reading or writing cannot proceed immediately, the operation can return instantly with a "no progress yet" signal, rather than blocking the thread while waiting for the resource to become ready. In Java NIO, examples include `SocketChannel` or `Pipe.SourceChannel` configured with `configureBlocking(false)`.
- **Asynchronous I/O** describes a model of **initiating an operation and receiving notification/results upon completion**: the method that submits the I/O request may return before the operation completes; the result arrives via a `Future` or `CompletionHandler`. In Java NIO.2, examples include `AsynchronousFileChannel` and `AsynchronousSocketChannel`.

The two models differ in **when the program learns that I/O is ready** and **when it learns that I/O has completed**. Both can help avoid dedicating a thread solely to wait on each connection, yet their actual behavior and code organization differ.

After this lesson, you will be able to:

1. Distinguish blocking, non-blocking, synchronous, and asynchronous by **API contract**.
2. Understand `Selector` along with `SelectionKey.OP_READ/OP_WRITE` in non-blocking I/O as a **readiness** mechanism, and `Future/CompletionHandler` in asynchronous I/O as a **completion** mechanism.
3. Write Java 17+ examples demonstrating non-blocking `Pipe.SourceChannel` and asynchronous `AsynchronousFileChannel`.
4. Understand why `Future.get()` can block, why a callback does not guarantee that the entire application uses no blocking I/O threads, and why readiness does not prove that a complete message has been read.
5. Choose the appropriate model for socket servers, file reading/writing, batch tasks, and libraries with blocking interfaces.

## 2. Four Commonly Confused Concepts

**Blocking** is when the calling thread is held until the operation condition occurs (or an error/timeout/cancellation happens). For example, a standard `InputStream.read()` may wait for data.

**Non-blocking** is when an I/O call returns without waiting for the resource to become ready. If reading/writing cannot proceed at that moment, the result may be `0`; the application must know **when to retry**, typically via a `Selector`.

**Synchronous** is when the caller directly receives the result of the ongoing operation before continuing the processing that depends on that result. For example, `FileChannel.read(buffer)` returns the number of bytes read when the call completes.

**Asynchronous** is when the caller submits work and the result is delivered later through a completion mechanism. For example, `AsynchronousFileChannel.read(buffer, position)` returns a `Future<Integer>`, or an overload taking a `CompletionHandler`.

These four terms do not form two absolute pairs of opposites. An application can run **blocking I/O on a worker thread** so that the higher-level calling interface appears asynchronous; the operation inside the worker is still blocking. An async API in Java can also be implemented using a synchronous mechanism underneath combined with a thread pool; the async contract describes **how the caller interacts with the result**, not a guarantee that the kernel never blocks any thread.

| Aspect | Non-blocking I/O | Asynchronous I/O |
| --- | --- | --- |
| Primary question | "Can I read/write **right now**?" | "Has the operation I requested **completed**?" |
| Signal | Channel readiness; `read/write` may return `0` | Completion: byte count/result or error via `Future`/handler |
| Typical Java APIs | `SocketChannel.configureBlocking(false)`, `Selector` | `AsynchronousSocketChannel`, `AsynchronousFileChannel` |
| Who advances the operation | Application calls `read()/write()` when notified ready | Provider executes the request; application receives completion result |
| Needs an event loop? | Usually has a selector loop for many channels | Can use callbacks/Future; does not mandate a single `Selector` |
| Read result | Calling `read(ByteBuffer)` directly returns `int` | `Future<Integer>` or `completed(Integer, attachment)` |
| Incomplete data | Maintain state and retry reading on subsequent readiness | Submit a new read operation after the previous one completes |
| How to avoid blocking the caller | Do not call blocking I/O operations on the event loop | Do not call `Future.get()` immediately on the event loop |

**No API promises to always read a complete application record in a single call.** Actual byte counts, EOF, buffer sizes, framing, and lifecycle must still be checked.

## 3. Readiness and Completion: Sequence Diagrams

### 3.1. Non-blocking with `Selector`: Readiness First, Perform I/O Later

```text
Thread/event loop             Selector              Socket/Pipe
      |                           |                      |
      | register(OP_READ)         |                      |
      |-------------------------->|                      |
      | select()                  |                      |
      |-------------------------->|                      |
      |    (wait for readiness)   |                      |
      |<------ readable key ------|<--- data arrives ----|
      | read(buffer)              |                      |
      |------------------------------------------------->|
      |<------------------ int n (n>0, 0, or -1) --------|
      | process n bytes; keep partial record             |
```

`Selector.select()` **can block the selector thread** while waiting for events; whereas the `read()/write()` operation itself on a **non-blocking channel** does not wait for the resource to be ready the way blocking mode does. Therefore, saying "non-blocking means no thread ever waits" is also incorrect.

If the program does not want to block at `select()`, there is `selectNow()` to check readiness without waiting. However, calling `selectNow()` repeatedly in a busy loop can consume CPU.

### 3.2. Asynchronous: Submit Request First, Receive Completion Later

```text
Application thread       AsynchronousFileChannel / provider
      |                                 |
      | read(dst, offset)               |
      |-------------------------------->|
      |<---------- Future --------------|
      | continue other work             |
      |                                 | perform I/O
      |            (upon completion)    |
      |<----------- completion ---------|
      | get() or completed()/failed()   |
      | process actual bytes read       |
```

With the overload returning `Future`, `future.get()` will **wait** if the result is not yet ready; calling it right after `read` turns the caller's execution flow into "submit then wait", even though the I/O API is still asynchronous.

With the `CompletionHandler` overload, the provider invokes `completed(result, attachment)` or `failed(error, attachment)` when the operation completes. The callback is the completion reception point; callback code should be brief and avoid running heavy CPU tasks that block the completion-handling thread for a long time.

### 3.3. Reactor and Proactor Are Pattern Names, Not Mandatory Java Types

**Reactor** is a way of organizing an application around readiness events (selector) where handlers themselves perform `read/write`. **Proactor** is a way of describing a model that receives completion after the system performs the requested I/O. Both terms are useful for architectural discussions, but you should not infer a one-to-one mapping to every JDK/OS implementation detail or treat API names as proof of kernel mechanisms.

## 4. How Does Non-blocking I/O Work in Java NIO?

Channels such as `SocketChannel`, `ServerSocketChannel`, `DatagramChannel`, and both ends of a `Pipe` are `SelectableChannel` instances. To register a channel with a selector:

```java
channel.configureBlocking(false);
SelectionKey key = channel.register(
        selector, SelectionKey.OP_READ);
```

This is a **non-standalone** snippet, assuming `channel` is an appropriate `SelectableChannel` and `selector` is open; imports and exception handling are needed.

If you register while the channel is still in blocking mode, `register` throws `IllegalBlockingModeException`. If you use an operation not supported by `channel.validOps()` (for example, registering `OP_WRITE` on a `Pipe.SourceChannel`), it may throw `IllegalArgumentException`.

Typical states:

- `ReadableByteChannel.read(ByteBuffer)` when data is read: returns a byte count `n > 0`.
- For a non-blocking channel, if no bytes are ready yet: **it may return `0`**.
- If the input has reached EOF: it returns `-1`; this is **not** simply a lack of data at the moment.
- `WritableByteChannel.write(ByteBuffer)` may write fewer bytes than remain in the buffer or return `0`. Unwritten bytes must still be retained to retry when notified writable.

`SelectionKey.isReadable()` does not guarantee that `read` will return enough bytes for an entire message. Readiness can change between the moment the selector selects the key and the moment I/O is executed, especially when multiple threads access the channel.

### Rules for a Selector Event Loop

1. Call `configureBlocking(false)` **before** registering.
2. Only register operation bits present in `validOps()`.
3. After `selector.select()`, iterate over `selectedKeys()` and **remove each processed key from the selected set**. `remove` differs from `key.cancel()`; cancel terminates the registration.
4. Check `key.isValid()` before operating on a key that might have been canceled.
5. For sockets, only keep `OP_WRITE` enabled when there is data to send; sockets are usually writable most of the time, so keeping it registered permanently easily causes the event loop to spin.
6. If another thread adds work while the selector is waiting, use a queue and `selector.wakeup()` properly.
7. Do not treat `select(timeout) == 0` as EOF; that is a selection state, not a channel read result.

## 5. Complete Java 17+ Example: Non-blocking `Pipe` with `Selector`

To avoid depending on network ports, the example uses an in-process `Pipe`. `Pipe.SourceChannel` is set to non-blocking and registered for `OP_READ`; the sink side writes the ASCII message `HELLO`. The program collects all 5 bytes even if each `read` receives only a portion.

Save as **`NonBlockingSelectorDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

public class NonBlockingSelectorDemo {
    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);
            source.register(selector, SelectionKey.OP_READ);

            byte[] expected = "HELLO".getBytes(StandardCharsets.US_ASCII);
            ByteBuffer outbound = ByteBuffer.wrap(expected);

            // Sink remains blocking; byte count is very small.
            while (outbound.hasRemaining()) {
                sink.write(outbound);
            }

            ByteArrayOutputStream received = new ByteArrayOutputStream();
            ByteBuffer inbound = ByteBuffer.allocate(8);

            while (received.size() < expected.length) {
                int keys = selector.select(2000);
                if (keys == 0) {
                    throw new IOException("Timeout while waiting for read");
                }

                Iterator<SelectionKey> it =
                        selector.selectedKeys().iterator();

                while (it.hasNext()) {
                    SelectionKey key = it.next();
                    it.remove();

                    if (!key.isValid() || !key.isReadable()) {
                        continue;
                    }

                    inbound.clear();
                    int n = source.read(inbound);
                    if (n == -1) {
                        throw new IOException("Unexpected EOF");
                    }
                    if (n > 0) {
                        inbound.flip();
                        while (inbound.hasRemaining()) {
                            received.write(inbound.get());
                        }
                    }
                }
            }

            System.out.println("bytes=" + received.size());
            System.out.println("text="
                    + received.toString(StandardCharsets.US_ASCII));
        }
    }
}
```

Run with JDK 17 or later:

```bash
javac NonBlockingSelectorDemo.java
java NonBlockingSelectorDemo
```

Stdout when the pipe/selector works normally:

```text
bytes=5
text=HELLO
```

**Key points:**

- `source.configureBlocking(false)` affects read calls on the **source channel**; the sink remains blocking. Having a `Selector` does not make every channel in the program non-blocking.
- `selector.select(2000)` can **block the event-loop thread for up to 2 seconds** waiting for readiness. This is expected selector behavior.
- When `OP_READ` fires, the program **itself calls** `source.read(inbound)`. If no bytes are available at the exact moment of reading, a non-blocking source can return 0.
- Only put the bytes actually read into `received`. `ByteBuffer.flip()` limits the range just received; `clear()` prepares for a new read cycle.
- `try-with-resources` closes both ends of the pipe and the selector.
- The example sets a timeout to avoid waiting indefinitely; on an overloaded system, a timeout `IOException` may appear instead of successful stdout.

This is an example of **readiness**; there is no `Future<Integer>` or completion callback performing the `read` on behalf of the application.

## 6. Asynchronous I/O in Java NIO.2

Notable APIs:

| API | How the result is received | Used for |
| --- | --- | --- |
| `AsynchronousFileChannel.read(dst, position)` | `Future<Integer>` | Reading a file by offset |
| `AsynchronousFileChannel.read(dst, position, attachment, handler)` | `CompletionHandler` | Reading a file by offset, receiving callback |
| `AsynchronousFileChannel.write(src, position)` | `Future<Integer>` | Writing a file by offset |
| `AsynchronousFileChannel.write(src, position, attachment, handler)` | `CompletionHandler` | Writing a file and receiving callback |
| `AsynchronousSocketChannel.connect(remote)` | `Future<Void>` or handler | TCP connection |
| `AsynchronousSocketChannel.read(dst)` | `Future<Integer>` or handler | Reading a socket |
| `AsynchronousSocketChannel.write(src)` | `Future<Integer>` or handler | Writing a socket |

`AsynchronousFileChannel` uses an **explicit offset**, not a shared `position()` cursor like `FileChannel`. This is convenient for operating at multiple positions, but requires you to manage offsets accurately and avoid uncoordinated overlapping write regions.

By contract:

- Submitting an I/O request via `read/write` does not mean the data has finished being read or written.
- A successful result is typically the **actual number of bytes processed**; it may be smaller than the requested buffer size, so looping or submitting subsequent requests is still necessary.
- Errors must be handled via `ExecutionException` from `Future.get()` or `CompletionHandler.failed(...)`.
- While an asynchronous operation has not completed, **do not modify the contents or `position/limit` of the buffer participating in the operation**. Reusing one buffer across multiple pending operations can result in undefined contents/state.
- With some asynchronous socket channels, submitting another read/write in the same direction while the previous operation is still pending can cause `ReadPendingException` / `WritePendingException`; the design must track pending state.
- Closing a channel while operations are pending must be handled with cancellation/exceptions and a clear cleanup policy.

`Future.get()` can block the calling thread; `Future.isDone()` only reports completion status, and calling it continuously in a busy-wait loop can also waste CPU.

## 7. Complete Java 17+ Example: Asynchronous File Read with `Future`

The program creates a small file, opens an `AsynchronousFileChannel`, submits a read request first, receives a `Future<Integer>`, and then intentionally calls `get()` to inspect the result for API learning purposes.

Save as **`AsyncFutureFileDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.Future;

public class AsyncFutureFileDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("nio-async-", ".txt");

        try {
            Files.writeString(file, "HELLO", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel channel =
                    AsynchronousFileChannel.open(
                            file, StandardOpenOption.READ)) {

                ByteBuffer buffer = ByteBuffer.allocate(8);

                Future<Integer> operation = channel.read(buffer, 0);
                System.out.println("request submitted");

                // Intentionally wait to demonstrate Future; caller can block.
                int n = operation.get();

                buffer.flip();
                byte[] bytes = new byte[buffer.remaining()];
                buffer.get(bytes);

                System.out.println("bytes=" + n);
                System.out.println("text="
                        + new String(bytes, StandardCharsets.US_ASCII));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Commands:

```bash
javac AsyncFutureFileDemo.java
java AsyncFutureFileDemo
```

Stdout when file I/O completes successfully:

```text
request submitted
bytes=5
text=HELLO
```

Explanation:

1. `channel.read(buffer, 0)` submits a request to read up to 8 bytes from offset 0 and **returns a Future**.
2. Printing `request submitted` only indicates that the submit call returned; it does not prove the operation completed at that instant.
3. `operation.get()` can block until the operation completes; therefore this example snippet is **not an end-to-end non-blocking event loop**.
4. The file contains only 5 bytes, so `n == 5` on success. `buffer.flip()` switches to reading the bytes placed into the buffer by the channel.
5. `try-with-resources` closes the channel, and then the temporary file is deleted.

If you only want to demonstrate correctness with a small file, `Future.get()` is convenient. In a GUI or an event loop handling thousands of connections, calling `get()` directly on a critical thread defeats the benefit the architecture is seeking.

## 8. Complete Java 17+ Example: Asynchronous with `CompletionHandler`

When you do not want to write code waiting on a `Future` right after each call, use the overload with `CompletionHandler`. This lesson uses `CountDownLatch` **only so the demo program waits for the callback to finish before printing the result and closing the file**. In a real server application, you usually chain tasks using callbacks, event queues, or a coordinator component rather than blocking a thread to wait on a latch.

Save as **`AsyncCallbackFileDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncCallbackFileDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("nio-callback-", ".txt");

        try {
            Files.writeString(file, "JAVA", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel channel =
                    AsynchronousFileChannel.open(
                            file, StandardOpenOption.READ)) {

                ByteBuffer dst = ByteBuffer.allocate(8);
                CountDownLatch done = new CountDownLatch(1);
                AtomicInteger readCount = new AtomicInteger(-2);
                AtomicReference<Throwable> error = new AtomicReference<>();

                channel.read(dst, 0L, "file-read",
                        new CompletionHandler<Integer, String>() {
                    @Override
                    public void completed(Integer n, String attachment) {
                        readCount.set(n);
                        done.countDown();
                    }

                    @Override
                    public void failed(Throwable exc, String attachment) {
                        error.set(exc);
                        done.countDown();
                    }
                });

                System.out.println("submitted=file-read");

                if (!done.await(10, TimeUnit.SECONDS)) {
                    throw new IOException("Timeout waiting for callback");
                }
                if (error.get() != null) {
                    throw new IOException("Asynchronous read failed",
                            error.get());
                }

                dst.flip();
                byte[] bytes = new byte[dst.remaining()];
                dst.get(bytes);

                System.out.println("bytes=" + readCount.get());
                System.out.println("text="
                        + new String(bytes, StandardCharsets.US_ASCII));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac AsyncCallbackFileDemo.java
java AsyncCallbackFileDemo
```

Stdout when completion succeeds:

```text
submitted=file-read
bytes=4
text=JAVA
```

In the handler, `completed(Integer, String)` receives the actual bytes read and the submitted `"file-read"` attachment, while `failed(Throwable, String)` receives the error. `CountDownLatch` ensures the thread printing the result proceeds only after the handler has updated the state. `AtomicInteger` and `AtomicReference` serve as simple result-passing holders in the demo; in real implementations, replace them with proper state and coordination mechanisms.

**Do not use callbacks as proof that no thread is waiting in the system.** The provider may use an underlying pool to carry out I/O work, and the demo code has `await` blocking the main thread. The benefit is that the API allows the caller **not to be forced to wait at the `read` call itself** and provides a separate completion-handling path.

A timeout on `await` does not automatically guarantee the I/O has been canceled. Real programs need a cancellation/closing policy and coordination for late completions; do not prematurely free or reuse the buffer while operations are still pending.

## 9. Why Does "Async" Not Mean "No Blocking Anywhere"?

There are at least three layers to consider:

1. **Caller-side API:** the method returns a `Future` or takes a handler, so the caller can continue other work instead of waiting for the entire I/O.
2. **How the provider executes:** it may rely on OS asynchronous I/O, or it may use a thread pool to execute blocking calls underneath. The Java contract does not promise a single implementation strategy across all operating systems, filesystems, and JVMs.
3. **How the application consumes the result:** calling `Future.get()` immediately, `CountDownLatch.await()`, or executing slow code inside the callback can keep the corresponding thread blocked.

Architectural example:

```text
HTTP / event-loop thread
    |
    | submit async file read
    v
Provider / executor: process I/O
    |
    | result/exception
    v
CompletionHandler or Future
    |
    v
Response system / scheduler
```

The model above can keep the HTTP thread free while I/O is in progress, but it does not mean the implementation uses no thread pool. To know the actual technology in use, check runtime documentation, profiling, and the execution environment.

Similarly, submitting `Files.readAllBytes(path)` to `ExecutorService.submit(...)` keeps **the caller from waiting immediately** upon submission, yet the worker still performs blocking I/O. This is **asynchronous orchestration** at the application layer, distinct from the guarantees of a **non-blocking channel**. Both approaches can be reasonable if goals and thread budgets are well managed.

## 10. File I/O: Why Doesn't `FileChannel` Use `Selector`?

`FileChannel` supports `ByteBuffer`, `position`, `size`, `map`, `transferTo`, and `force`. However, **`FileChannel` is not a `SelectableChannel`**: it has no `configureBlocking(false)` or `register(selector, ops)`.

```java
FileChannel file = FileChannel.open(path, StandardOpenOption.READ);

// The following two lines DO NOT compile:
// file.configureBlocking(false);
// file.register(selector, SelectionKey.OP_READ);
```

This is an **intentionally invalid illustration**, not a runnable example; it shows clearly why `Selector` cannot be used for `FileChannel`.

If you need to process files without forcing the calling thread to wait:

- `AsynchronousFileChannel` provides `Future`/`CompletionHandler`.
- Or run synchronous file I/O in a worker thread/executor and pass the result back to the event loop.
- If the goal is to **receive notifications when a file is modified**, consider `WatchService` to observe directory change events; it is not a byte-level selector for files and does not replace actual file reading.

**Do not conclude** that because an "API is named NIO," every channel is non-blocking or can register with a selector. NIO contains synchronous interfaces, readiness-based non-blocking interfaces, and completion-based asynchronous interfaces.

## 11. TCP Server: Which Model to Choose?

### 11.1. Non-blocking `SocketChannel` + `Selector`

A server typically has one or a few event-loop threads:

1. Open `ServerSocketChannel` and call `configureBlocking(false)`.
2. `register(selector, OP_ACCEPT)` to watch for new connections.
3. When a key is acceptable, call `accept()`; the new `SocketChannel` must also have `configureBlocking(false)` called and then be registered.
4. When readable, call `read(ByteBuffer)`, check `n > 0 / n == 0 / n == -1`, and assemble chunks into messages.
5. When there is data to send, perform `write(ByteBuffer)`. If partially written, keep the remainder and enable `OP_WRITE`; disable `OP_WRITE` when the output queue is empty.
6. When a key is canceled or a channel is closed, release resources according to the lifecycle.

`OP_READ` only notifies that you can attempt to read. Do not treat a ready key as a complete HTTP request or a complete binary protocol frame.

### 11.2. `AsynchronousServerSocketChannel` / `AsynchronousSocketChannel`

Asynchronous socket APIs use `Future` or `CompletionHandler` for `accept`, `connect`, `read`, and `write`. The program does not use `Selector` directly to pick readiness keys; it receives **completion** for each submitted operation.

Conceptual example (snippet):

```java
socket.read(buffer, buffer, new CompletionHandler<Integer, ByteBuffer>() {
    @Override
    public void completed(Integer n, ByteBuffer dst) {
        // n: number of bytes received, or -1 for EOF.
        // After processing the read portion, submit another read if needed.
    }

    @Override
    public void failed(Throwable error, ByteBuffer dst) {
        // Record the error and terminate/close the connection per policy.
    }
});
```

This is a **non-standalone snippet**: `socket` is a connected `AsynchronousSocketChannel`, `buffer` is a valid `ByteBuffer`, and imports plus a lifecycle management policy are needed. It illustrates the completion point, not a complete TCP server.

Both approaches still require framing, backpressure, memory limits, timeouts, cancellation, error observability, and cleanup. Choose based on existing APIs/frameworks, operability, measured performance, and manageable complexity; there is no rule that asynchronous is always faster than non-blocking in every case.

## 12. Key Differences Between Readiness and Completion When Handling Buffers

| Situation | Readiness / non-blocking | Completion / async |
| --- | --- | --- |
| Who performs `read`? | Application handler calls `channel.read(buffer)` when ready | Application submits `channel.read(...)`; provider processes request |
| When does buffer `position` change? | During the `read()` call when bytes are available | During the async operation; should only access/flip upon completion |
| No bytes right now | `read` may return `0` | Request may remain pending; result arrives later |
| End of input | `read` may return `-1` | Completion carries `-1` on EOF |
| Partial write | `write` may write partially/0; enable OP_WRITE and retry | Completion carries actual bytes written; submit next write for remainder |
| Error | Usually thrown directly from `read/write` | Future fails or `failed` callback is invoked |
| When can the buffer be reused? | After the synchronous call completes, with proper state | After **completion** and after the application properly consumes the data |

A serious bug in async code is:

```java
Future<Integer> result = asyncFile.read(buffer, 0);
// Wrong if I/O is still pending:
buffer.clear();
buffer.put(newData);
```

This is **intentionally incorrect code**, because the buffer belongs to a still-pending read operation. Changing its contents, position, or limit too early can yield wrong results or leave the buffer state undefined. Wait for completion before `flip()`, parsing, or reusing the buffer.

Conversely, in a non-blocking channel, once `read(buffer)` returns, that call is finished; however, it may have read only part of a message. The program still has to retain enough state to receive the remaining bytes on later readiness events.

## 13. Timeouts, Cancellation, and Errors

### Non-blocking

- `selector.select(timeout)` waits for readiness up to the specified duration; a return value of 0 does not by itself indicate channel EOF.
- `selectNow()` does not wait; use it when the event loop has other work, not in a busy-wait loop.
- `selector.wakeup()` causes a currently waiting select or the next select call to return according to contract.
- `SelectionKey.cancel()` cancels the registration, and does not itself close the channel.
- `channel.close()` closes the I/O resource and cancels corresponding registrations.
- `read()==-1` indicates channel EOF, unlike `read()==0` which means no progress in that non-blocking read call.

### Asynchronous

- `Future.get(timeout, unit)` waits up to the specified duration and may throw `TimeoutException`; a timeout **does not prove the underlying I/O operation was canceled**.
- `Future.cancel(mayInterruptIfRunning)` requests cancellation under the Future contract; the result/behavior for an in-progress operation depends on the API and state. Do not assume resources are rolled back, the channel remains usable, or the buffer is immediately untouched after cancel.
- `ExecutionException` wraps the underlying cause when waiting in `get()`; `InterruptedException` signals the waiting thread was interrupted.
- `CompletionHandler.failed(Throwable, attachment)` receives errors as a callback. If the callback itself throws an exception, understand how the provider logs/handles errors; do not use callbacks to swallow failures.
- `channel.close()` while operations are pending can lead to failed completions or cancellations per the API; the application needs a shutdown procedure and protection for buffers/state.

When durable data writes are required, neither readiness nor completion **automatically replaces `FileChannel.force()`, `FileDescriptor.sync()`, or a commit protocol**. "I/O completed" means the I/O operation in the contract finished, not necessarily a guarantee against power loss.

## 14. Thread Pools, Backpressure, and Resource Limits

Neither model is free:

**For non-blocking selectors:**
- One event loop can monitor many connections, but a handler doing heavy CPU work or blocking I/O on the event loop slows down all associated connections.
- Ignoring partial writes causes lost bytes; keeping `OP_WRITE` enabled continuously when the queue is empty can spike CPU.
- Readiness can arrive faster than message processing speed, requiring bounded input buffers, temporarily disabling `OP_READ`, and backpressure design.

**For asynchronous I/O:**
- Even though the API returns a Future/callback, the implementation may use an executor; a pool that is too small or an unbounded queue can introduce latency.
- Callbacks should not perform long-running blocking work on the completion-handling thread. If needed, offload to a separate executor with bounded work.
- Do not submit an unbounded number of concurrent operations on the same channel/buffer. Track in-flight operations, buffer ownership, and capacity limits.
- A mechanism is needed to signal results back to the coordinating thread, handle exceptions, and shut down cleanly.

**For blocking tasks in a worker pool:** the event loop can continue doing other work, yet the worker pool remains bounded by thread count and device speed. This model is a useful tool when the system relies on existing blocking libraries under moderate load; it does not turn an `InputStream` into a `SelectableChannel`.

There is no universal figure proving one model is always faster. Measure throughput, latency (especially p95/p99), thread counts, CPU, queue size, connection count, and operation duration in the real runtime environment.

## 15. Practical Selection Scenarios

| Requirement | Commonly Suitable Choice | Reason |
| --- | --- | --- |
| A CLI reading a small file | Synchronous `Files.readAllBytes` / `FileChannel` | Simple code, few tasks |
| HTTP server with many TCP sockets and an event loop | Non-blocking `SocketChannel` + `Selector` or equivalent framework | Coordinates readiness across many channels |
| Reading/writing files at offsets without forcing caller to wait | `AsynchronousFileChannel` or executor task | Provides Future/handler or offloads blocking task |
| Application handling socket completion callbacks | `AsynchronousSocketChannel` / `AsynchronousServerSocketChannel` | Callback/Future model per operation |
| Using a blocking `InputStream` library from a UI thread | Offload work to a worker thread | Keeps UI thread free; I/O on worker remains blocking |
| Watching a log file for updates | `WatchService` combined with actual file reading | Filesystem events differ from socket readiness |
| Multiple file writes requiring durability | Appropriate I/O + `force/sync` and data protocol | Completion/readiness is not durability |
| A request requiring data that arrives in pieces | Framing + state/buffer suited to chosen model | Both models can receive partial data |

Do not convert all code to async simply because any I/O can be slow. Choose the model based on how the system handles concurrency, the framework in use, connection count requirements, state management capability, and environment limits.

## 16. Common Pitfalls

1. **"Async and non-blocking are the same."** False: non-blocking answers readiness/whether I/O can be tried immediately; async provides a mechanism to receive completion after submission.
2. **"`Selector.select()` never blocks."** False: `select()` can block the thread waiting for events; non-blocking describes the I/O calls of properly configured channels.
3. **"`isReadable()` means reading is done."** False: the selector only reports readiness; the application must call `read()` and check the result.
4. **"AsynchronousFileChannel uses `Selector`."** False: it is a completion API, not a `SelectableChannel`.
5. **"`FileChannel` also has `configureBlocking(false)`."** False: `FileChannel` is not selectable and lacks that API.
6. **"`Future.get()` does not block because the Future comes from async."** False: `get()` can wait until the operation completes.
7. **"Callbacks prove no OS thread is ever blocked."** False: the implementation may use a thread pool underneath.
8. **"One read always gets the whole message."** False in both models; the result may be smaller than expected, requiring framing.
9. **"You can `flip()/clear()` a buffer right after submitting async."** False while the operation is pending; wait for completion before reusing it.
10. **"If non-blocking write returns 0, just retry in an infinite while loop."** Bad practice: use readiness/`OP_WRITE` and backpressure to avoid CPU spinning.
11. **"Keep OP_WRITE enabled permanently to make sure everything is sent."** Unnecessary and easily triggers continuous events whenever the socket is writable, increasing CPU usage.
12. **"Future timeout cancels the operation."** False; a timeout only limits how long the caller waits.
13. **"Callback completion means the file survived power loss."** Not by default; durability requires a separate storage sync contract.
14. **"Spawning unlimited async tasks scales infinitely."** False: executors, descriptors, buffers, and queues all have limits.
15. **"Read/write returning `0` and `-1` are equivalent."** False: 0 means no progress in that call, -1 means EOF on the read path.

## 17. Exercises and Self-Check Questions

1. Explain the difference between "a channel is ready to read" and "a read request has completed." Through which Java APIs is each status received?
2. Why can `selector.select()` block while `SocketChannel.read()` calls on a non-blocking channel do not wait for data readiness as in blocking mode?
3. You registered `OP_READ` on a socket. Does `isReadable() == true` guarantee `read(buffer)` returns the exact 100 bytes expected?
4. If `AsynchronousFileChannel.read(buffer, 0)` returns a `Future<Integer>`, what happens if `future.get()` is called directly on the UI thread?
5. Why might a thread pool be running I/O underneath an API named `AsynchronousFileChannel`?
6. A non-blocking socket cannot write yet so `write(buffer) == 0`. How should `OP_WRITE` be used to retry without busy-spinning the CPU?
7. Can `FileChannel` be registered with a selector? If you want to read a file on a background task, what two options can you choose?
8. In `AsyncCallbackFileDemo`, why must you wait for completion before calling `dst.flip()` and before closing the channel?
9. If a callback returns `completed(20, attachment)` but the protocol requires 80 bytes, what should the program do?
10. Does `Future.get(timeout)` timing out mean the buffer contents are immediately safe to reuse? How should the lifecycle be managed?
11. How do you distinguish `read()==0` and `read()==-1` on a non-blocking socket?
12. Try modifying `NonBlockingSelectorDemo` so the sink sends multiple parts, observe the `select` loop, and explain why the byte count received in each turn may differ.
13. Try changing `AsyncFutureFileDemo` to use a callback; what differs in how the application receives the result and handles errors?
14. If you need durable writes to a file, is asynchronous completion sufficient on its own? Why?
15. Which I/O style would you choose for a server with 50,000 sockets and an infrequent small configuration file read? Explain why file work should be separated from the event loop.

## 18. Java SE 17 API References

- [`SelectableChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html) — `configureBlocking`, `register`, and operation validity.
- [`Selector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html) — `select`, `selectedKeys`, `wakeup`.
- [`SelectionKey`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html) — `interestOps`, `readyOps`, and operation bitmasks.
- [`AsynchronousFileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html) — file I/O with `Future` and `CompletionHandler`.
- [`AsynchronousSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html) — completion-based TCP connect/read/write.
- [`CompletionHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html) — success/failure callbacks.

## 19. Key Takeaways

**Non-blocking I/O** prevents I/O calls from waiting for data/resources to become ready; the application uses a `Selector` to be notified of **readiness** and then **attempts `read()/write()` itself**. **Asynchronous I/O** lets you submit a request and receive **completion** as a `Future` or `CompletionHandler`; the provider executes the I/O request via its underlying mechanism.

Both models still have to handle partial I/O, EOF, buffer ownership, timeouts, cancellation, backpressure, and resources. `Future.get()` can block the calling thread; `Selector.select()` can also wait for readiness. "Async" does not promise the provider avoids blocking threads, and "non-blocking" does not mean nothing in the application can ever block. Choose the API based on **the signal you need (ready vs. completed)**, the resource type (file/socket), and how the application coordinates work.
