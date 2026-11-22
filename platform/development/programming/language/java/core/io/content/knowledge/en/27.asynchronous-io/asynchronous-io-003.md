# Future and CompletionHandler in Java NIO.2: Two Ways to Receive Asynchronous I/O Results

## 1. Problem and Objectives

With familiar synchronous I/O, a `channel.read(buffer)` call normally returns only when the read operation has a result. Java NIO.2 provides asynchronous channels in the `java.nio.channels` package, allowing you to **initiate an I/O operation and receive the result later**.

Notable classes include:

- `AsynchronousFileChannel`: reads/writes file regions at specific offsets.
- `AsynchronousSocketChannel`: connects, reads, and writes over TCP asynchronously.
- `AsynchronousServerSocketChannel`: accepts TCP connections asynchronously.

The two primary API styles are **`Future`** and **`CompletionHandler`**:

1. **`Future`:** the I/O method returns an object representing an incomplete result; the application checks status or calls `get()` to wait for and retrieve the result.
2. **`CompletionHandler`:** when calling I/O, the application passes a callback; when the operation finishes, the system invokes `completed(...)` or `failed(...)`.

**Asynchronous does not mean data is guaranteed to be ready immediately**, that the operation always runs on a new thread, or that each read/write transfers the full requested byte count. What matters is knowing when the work completes, what the actual result is, and who manages buffer/channel lifetimes.

After this lesson, you will understand how to choose between `Future` and `CompletionHandler`, handle partial reads/writes, errors, timeouts, operation cancellation, and write standalone runnable Java 17+ examples.

## 2. Comparing API Signatures

### 2.1. `AsynchronousFileChannel`

Both methods perform reading at an explicit offset but use different result-delivery models:

~~~java
// Future: result is retrieved from the Future<Integer> object.
Future<Integer> read(ByteBuffer dst, long position);

// Callback: the system delivers the result to CompletionHandler.
<A> void read(
        ByteBuffer dst,
        long position,
        A attachment,
        CompletionHandler<Integer, ? super A> handler);
~~~

Similarly for write operations:

~~~java
Future<Integer> write(ByteBuffer src, long position);

<A> void write(
        ByteBuffer src,
        long position,
        A attachment,
        CompletionHandler<Integer, ? super A> handler);
~~~

These are **simplified method signatures for learning**, not standalone Java programs. `position` is the offset measured in **bytes within the file**, not `ByteBuffer.position()` and not a shared file cursor position.

With `AsynchronousFileChannel`, there is no "current file position" concept to rely on like `FileChannel.position()`: each read/write call uses an explicit offset. When an operation returns `n` bytes, the next call processes the remainder at `position + n`.

### 2.2. `AsynchronousSocketChannel`

~~~java
Future<Void> connect(SocketAddress remote);
<A> void connect(
        SocketAddress remote,
        A attachment,
        CompletionHandler<Void, ? super A> handler);

Future<Integer> read(ByteBuffer dst);
<A> void read(
        ByteBuffer dst, A attachment,
        CompletionHandler<Integer, ? super A> handler);

Future<Integer> write(ByteBuffer src);
<A> void write(
        ByteBuffer src, A attachment,
        CompletionHandler<Integer, ? super A> handler);
~~~

These are also **illustrative signatures**; some APIs have additional overloads for timeouts or multiple buffers. Unlike file channels, sockets have no file offset; bytes are received/sent sequentially over a TCP stream.

| Characteristic | `Future` | `CompletionHandler` |
| --- | --- | --- |
| Receiving result | Call `future.get()` or check `isDone()` | Callback `completed(result, attachment)` |
| I/O error during execution | Usually wrapped in `ExecutionException` when calling `get()` | Callback `failed(exc, attachment)` |
| Waiting for completion | `get()` **blocks the calling thread**; has timeout variants | Does not need to block the initiating thread just to wait for the result |
| Coordinating multiple steps | Easy to write sequentially, but waiting must be managed | Can chain steps from callbacks, or bridge to `CompletableFuture` |
| Common risks | Calling `get()` immediately and accidentally blocking an important thread | Long callbacks, errors not propagated to observers, or tangled control flow |
| Cancellation | `Future.cancel(...)` provides a cancellation request interface | No `Future` object returned by the callback overload |
| Attaching context | Maintain state externally alongside the `Future` | Use `attachment` to pass state to the callback |

A method using a `Future` overload **does not simultaneously** invoke a `CompletionHandler` from another overload. The two styles express the same idea of asynchronous results, yet how completions are received and coordinated differs.

## 3. Timeline of an Asynchronous Operation

With `Future`:

~~~text
Calling thread:
  create ByteBuffer
       |
  Future<Integer> f = channel.read(buffer, offset)
       |
  process other independent work (if any)
       |
  f.get()  -- may have to wait -->
       |
  read actual byte count; handle buffer/EOF/error
~~~

With `CompletionHandler`:

~~~text
Initiating thread:
  channel.read(buffer, offset, state, handler)
       |
  continue running other work

When I/O finishes:
  handler.completed(n, state)
       or
  handler.failed(error, state)
~~~

**Very common confusion:** `channel.read(...)` returning a `Future` quickly does not mean the read has completed. Conversely, a callback running later does not mean it always runs on a dedicated thread per request; the execution policy depends on the provider and channel group.

## 4. Using `Future` Properly

### 4.1. Initiate First, Receive Result Later

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);
Future<Integer> pending = file.read(buffer, 0L);

// Other work can be done here.
int n = pending.get(); // Blocks the calling thread if I/O is not finished yet.
~~~

This snippet uses an already-open `AsynchronousFileChannel file` and requires importing `ByteBuffer` and `Future`. `get()` may throw `InterruptedException` or `ExecutionException`; this example only illustrates the operation flow.

Key methods:

- `future.isDone()`: indicates the operation has reached a terminal state (success, failure, or canceled), **not necessarily success**.
- `future.get()`: waits and retrieves the result; execution errors are wrapped in `ExecutionException`.
- `future.get(timeout, unit)`: limits **how long the calling thread waits**; may throw `TimeoutException`.
- `future.cancel(mayInterruptIfRunning)`: requests cancellation; may return `false` if unable to cancel. After cancellation, `get()` may throw `CancellationException`.
- `future.isCancelled()`: checks the cancellation status of the Future.

**A wait timeout does not necessarily stop the I/O.** After `get(2, SECONDS)` throws `TimeoutException`, the read/write operation may still be running. The application must decide whether to keep waiting, request cancellation, or close resources; do not reuse the `ByteBuffer` as though I/O has ended.

### 4.2. Distinguishing Initiation Errors from Execution Errors

Some errors can occur **immediately at the `read/write` call**, such as invalid arguments or an already-closed channel. Others arise after the operation starts:

~~~java
try {
    Future<Integer> f = file.read(buffer, offset);
    int n = f.get();
    // Handle n: n>0, n==0, or n==-1 (for reading).
} catch (ExecutionException ex) {
    Throwable actualCause = ex.getCause();
    // Log/map the error from the I/O task.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Respect the calling thread's cancellation policy.
}
~~~

This is an illustrative snippet with `file`, `buffer`, and `offset` already declared and `Future` and `ExecutionException` imported. Valid method-level exceptions must also be handled when used in a real program.

**Do not swallow `InterruptedException`:** restore the interrupt flag via `Thread.currentThread().interrupt()` or propagate the error according to application policy. `get()` being interrupted does not by itself prove the I/O was canceled.

## 5. Using `CompletionHandler` Properly

A `CompletionHandler<V,A>` has two type parameters:

- `V` is the **result type** of one I/O operation, typically `Integer` for bytes read/written or `Void` for connect.
- `A` is the **attachment type** chosen by the caller to carry context such as request id, offset, buffer, state, or a tracking object.

~~~java
channel.read(buffer, 0L, requestId,
    new CompletionHandler<Integer, String>() {
        @Override
        public void completed(Integer bytesRead, String id) {
            System.out.println(id + ": " + bytesRead);
        }

        @Override
        public void failed(Throwable error, String id) {
            System.err.println(id + ": " + error);
        }
    });
~~~

This is an illustrative snippet; `channel` is an `AsynchronousFileChannel`, `buffer` is a `ByteBuffer`, `requestId` is a `String`, and `CompletionHandler` must be imported. The `completed` callback only indicates that **one operation** finished; if `bytesRead` is incomplete, you must initiate the next read yourself.

### 5.1. What Should a Callback Do?

Inside `completed`:

1. Check the actual number of bytes read/written.
2. Update the buffer and offset or protocol state.
3. If more data remains to be processed, initiate the next operation.
4. When the entire request is complete, notify the waiting component or emit the result.

Inside `failed`:

1. Record the actual cause.
2. Mark the task as failed **once**.
3. Release/close resources according to the ownership policy.

Do not perform heavy CPU work, sleep, or hold long locks inside a callback if that occupies a shared thread used to complete other I/O operations. Offload heavy work to an appropriate executor.

### 5.2. Attachments Help Prevent Mixing Up State

When multiple I/O operations happen concurrently, the attachment lets each callback know which operation it belongs to:

~~~java
record RequestState(String id, long fileOffset) {}

RequestState state = new RequestState("req-42", 4096L);
channel.read(buffer, state.fileOffset(), state,
    new CompletionHandler<Integer, RequestState>() {
        @Override
        public void completed(Integer result, RequestState request) {
            System.out.println(request.id() + " -> " + result);
        }

        @Override
        public void failed(Throwable exc, RequestState request) {
            System.err.println(request.id() + ": " + exc);
        }
    });
~~~

This is an illustrative snippet for Java 17+, with `channel`/`buffer` already open and `CompletionHandler` imported. When continuing with remaining bytes, update the offset based on **the actual number of bytes transferred**, not the originally requested size.

An attachment does not by itself resolve thread contention or shared-buffer races; mutable state still requires proper ownership or synchronization.

## 6. Actual Results and Partial Read/Write Loops

For `AsynchronousFileChannel.read(dst, position)`:

- `n > 0`: `n` bytes were placed into the buffer; `ByteBuffer.position()` increases by `n`.
- `n == -1`: EOF, no more bytes at the requested read position.
- `n == 0`: no bytes were transferred this time; the buffer may have no space left or a no-progress situation occurred. **Do not treat `0` as having enough data**.

For `write(src, position)`:

- `n > 0`: `n` bytes were written, `src.position()` increases accordingly.
- `n == 0`: zero bytes transferred; a retry/backoff policy or error reporting is needed for the workload.
- Writing has no `-1` value to represent EOF as reading does.

### 6.1. `Future` Pattern for Writing an Entire Buffer

~~~java
long fileOffset = 0L;

while (src.hasRemaining()) {
    Future<Integer> f = file.write(src, fileOffset);
    int n = f.get();

    if (n <= 0) {
        throw new IOException("Không có tiến triển khi ghi");
    }

    fileOffset += n;
}
~~~

This is an illustrative snippet with `file` as an `AsynchronousFileChannel` opened for writing and `src` as a `ByteBuffer` containing data; `get()`'s checked exceptions must be handled per context. The complete sample program in the next section demonstrates this usage.

**Dangerous mistake:** initiating multiple `write` calls on **the same ByteBuffer** before the previous operation completes and advancing the offset by the requested byte count. Concurrent buffer access can leave data/positions undefined contrary to expectations. In sequential examples, issue the next operation only after receiving the current one's result.

### 6.2. Callback Pattern for Reading a Target Byte Count

Idea:

~~~text
Read at offset p into buffer
  |
  +-- n > 0, buffer still has space: read next at p + n
  |
  +-- n > 0, buffer is full enough: report success
  |
  +-- n == -1: report premature EOF if bytes are still missing
  |
  +-- n == 0: apply no-progress policy
  |
  +-- failed(error): report error
~~~

Remember that `CompletionHandler.completed(n, attachment)` corresponds to **a single read operation**, not always an entire message or the entire file.

## 7. Complete Java 17+ Example: Future for Writing, CompletionHandler for Reading

The standalone runnable program below creates a temporary file, uses `Future<Integer>` to write all of `HELLO` to the file, and then uses `CompletionHandler` to read all 5 bytes. The callback result is bridged to a `CompletableFuture` so the main thread can wait for completion and print results in order.

**Save the code as `AsyncIoFutureHandlerDemo.java`:**

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class AsyncIoFutureHandlerDemo {

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("async-io-", ".txt");

        try {
            try (AsynchronousFileChannel channel =
                         AsynchronousFileChannel.open(
                                 file,
                                 StandardOpenOption.READ,
                                 StandardOpenOption.WRITE)) {

                ByteBuffer src = ByteBuffer.wrap(
                        "HELLO".getBytes(StandardCharsets.UTF_8));

                long offset = 0L;
                while (src.hasRemaining()) {
                    Future<Integer> pending = channel.write(src, offset);
                    int n = pending.get();

                    if (n <= 0) {
                        throw new IOException("Future write không tiến triển");
                    }
                    offset += n;
                }

                System.out.println("Future bytes written: " + offset);

                ByteBuffer dst = ByteBuffer.allocate(5);
                CompletableFuture<Integer> done = readFully(
                        channel, dst, 0L);

                int readBytes = done.get(5, TimeUnit.SECONDS);
                dst.flip();

                System.out.println("Handler bytes read: " + readBytes);
                System.out.println("Content: "
                        + StandardCharsets.UTF_8.decode(dst));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static CompletableFuture<Integer> readFully(
            AsynchronousFileChannel channel,
            ByteBuffer dst,
            long fileOffset) {

        CompletableFuture<Integer> done = new CompletableFuture<>();

        channel.read(dst, fileOffset, fileOffset,
                new CompletionHandler<Integer, Long>() {
                    private int total;

                    @Override
                    public void completed(Integer n, Long currentOffset) {
                        if (n == -1) {
                            done.completeExceptionally(
                                    new EOFException("Tệp kết thúc sớm"));
                            return;
                        }

                        if (n == 0) {
                            done.completeExceptionally(
                                    new IOException("Đọc không tiến triển"));
                            return;
                        }

                        total += n;
                        if (!dst.hasRemaining()) {
                            done.complete(total);
                            return;
                        }

                        long nextOffset = currentOffset + n;
                        try {
                            channel.read(
                                    dst, nextOffset, nextOffset, this);
                        } catch (RuntimeException ex) {
                            done.completeExceptionally(ex);
                        }
                    }

                    @Override
                    public void failed(Throwable error, Long ignoredOffset) {
                        done.completeExceptionally(error);
                    }
                });

        return done;
    }
}
~~~

Run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 AsyncIoFutureHandlerDemo.java
java AsyncIoFutureHandlerDemo
~~~

**Expected stdout when I/O completes normally:**

~~~text
Future bytes written: 5
Handler bytes read: 5
Content: HELLO
~~~

### Code Explanation and Correctness

1. `Files.createTempFile` creates an empty file with a different generated name each run. Because stdout does not print the filename, the displayed output is stable.
2. `AsynchronousFileChannel.open` opens the channel with read and write permissions. There is no file-channel `position()`; each call supplies the file offset.
3. `Future<Integer> pending = channel.write(src, offset)` initiates a write. `pending.get()` waits until the actual byte count is available, then `offset += n` continues with the remainder. `src.position()` has also advanced by the number of bytes written.
4. `ByteBuffer.wrap(...)` supplies the exact 5 UTF-8 bytes of `HELLO`. Even if each call writes only a portion, the loop writes everything before reading starts.
5. `readFully(...)` initiates the first read and returns a `CompletableFuture` representing **the entire read process**, including subsequent reads if a callback returns fewer bytes than needed.
6. Whenever `completed(n, currentOffset)` receives `n > 0`, the buffer has already updated `position`, so the next read uses **the same buffer** but with file offset `currentOffset + n`. Do not advance `dst.position()` a second time manually.
7. Once all 5 bytes are read, the callback calls `done.complete(total)`. Upon premature EOF, lack of progress, or I/O error, the callback uses `completeExceptionally(...)`.
8. `done.get(5, SECONDS)` only lets the main thread wait and enforces a wait time limit; callbacks run on the channel's I/O handling infrastructure. A timeout does not by itself prove the operation was canceled.
9. After completion, `dst.flip()` switches the buffer to read mode to decode the exact 5 bytes. The program uses ASCII within UTF-8, so there are no partial multi-byte characters.
10. `try-with-resources` closes the channel, and `finally` deletes the temporary file. If an exception occurs, the program does not pretend it succeeded.

**Intentional limitation of the example:** if the file is stable and the buffer still has space yet the read returns `0`, the example reports an error to avoid a non-advancing loop. A network application or changing source needs its own retry/readiness/timeout policy. When a timeout occurs, the program exits `try-with-resources` and closes the channel; real shutdown/cancellation handling must be explicitly designed in production systems.

## 8. `Future` Does Not Mean "Completely Non-blocking Application"

The declaration:

~~~java
Future<Integer> f = channel.read(dst, 0);
int n = f.get();
~~~

is I/O **initiated asynchronously**, but **the calling thread becomes synchronously blocked at `get()`**. Calling `get()` right after every operation produces thread-usage behavior very similar to sequential reading.

`Future` remains useful when:

- Initiating I/O and processing independent work before needing the result.
- Submitting multiple operations **on independent buffers**, storing the Futures, and awaiting them later.
- Passing Futures to another coordinator and letting a dedicated worker await results.
- Using timeouts at request boundaries when the thread model permits waiting.

**`isDone()` + continuous polling** is usually bad practice: it creates a busy-spin and makes timeouts awkward. Replace it with `get(timeout, unit)` on a thread allowed to wait, or use callbacks to be notified upon completion.

## 9. `CompletionHandler` Does Not Automatically Chain Futures or Bound Load

A callback can "chain" operations by calling `read/write` again inside `completed`. However, with tens of thousands of connections or requests, the application still must manage:

- **In-flight operations:** bound the number of concurrent requests and total live bytes/buffers.
- **Ownership:** who is allowed to read/modify a buffer while an operation is not yet complete.
- **Deadlines:** if a peer stops responding, the callback might not arrive within the desired timeframe; controlled timeout/cancellation/closing is needed.
- **Errors:** the `failed` callback must route to logs, request state, or a failed Future; throwing an exception out of a callback is not equivalent to throwing from the initiating line of code.
- **Resource closing:** a channel may be closed while operations are pending; callbacks/futures must handle abnormal termination.
- **Business ordering:** callbacks of independent operations can complete **out of initiation order**, even if data must be published in order.

**Do not use a single mutable `ByteBuffer` for multiple concurrent I/O operations** without a specialized synchronization design. In practice, using a separate buffer per request or coordinating a sequence of operations so only one I/O operation touches the buffer at a time is much easier to verify.

## 10. Differences Between Asynchronous File and Socket I/O

### 10.1. File: Independent Offsets

`AsynchronousFileChannel.read(dst, position)` reads by the supplied byte offset. Two reads at offsets 0 and 4096 are two distinct requests; they may complete in a different order and must have independent buffers if running concurrently.

Note that Java may implement asynchronous file I/O using a thread pool and regular OS operations depending on the platform. **There is no guarantee every operation is kernel-native async/zero-copy**, nor a guarantee of speedup for every workload. If performance is the goal, measure throughput, CPU, context switches, concurrency, and latency.

### 10.2. Socket: Byte Stream and Backpressure

`AsynchronousSocketChannel` uses a TCP byte stream. One `read` may return fewer bytes than a message's length; one `write` may send fewer bytes than remain in the buffer. **Message framing** such as length-prefixing or delimiters is required if the protocol defines discrete messages.

Characteristic errors to remember:

- `ReadPendingException`: attempting to initiate another read while the socket already has an unfinished read operation.
- `WritePendingException`: the same for the write direction.
- `NotYetConnectedException`: reading/writing before the connection has been established.
- `AsynchronousCloseException`/`ClosedChannelException`: closing the channel can affect pending operations.

Consequently, with sockets you typically build a **read loop** continuing after each received result and a **write queue** sending buffers one after another; do not fire multiple `read` calls in parallel on the same `AsynchronousSocketChannel` hoping they queue themselves in order.

`Future<Void> connect(...)` yields a `Void` result; when connection succeeds, `get()` returns `null`. With a connect callback, `completed(null, attachment)` only indicates the connect operation finished, not that the server has processed any request.

## 11. Executors, Thread Pools, and Callback Safety

Java NIO.2 uses thread groups (asynchronous channel groups) or executors depending on the API and channel type. For example:

- `AsynchronousFileChannel.open(path, options, executor, attrs...)` has an overload accepting an `ExecutorService`.
- `AsynchronousChannelGroup.withFixedThreadPool(...)` can provide a group for asynchronous socket/server channels.

**Do not attach a separate executor to each small operation**: it easily causes thread explosion, high memory usage, and context-switch overhead. Design executors/groups around the application or service lifecycle.

If callbacks share counters or state across threads, ensure memory safety using ownership, `AtomicInteger`, synchronization, immutable data, or appropriate coordination mechanisms. `CompletableFuture.complete(...)` provides a convenient result-publication point; however, mutable objects like `ByteBuffer` still require the rule of accessing them only after I/O completes.

### A Note on Deadlock and Starvation

Do not call `future.get()` inside a callback if that Future can only complete when another task running on the same executor—whose workers you have all blocked—executes. That can lead to starvation/deadlock.

Also do not run multi-second heavy data analysis inside a callback on a shared I/O executor. Offload heavy CPU processing to a compute executor if needed.

## 12. Timeouts, Cancellation, and Lifecycle

### 12.1. Waiter Timeout

~~~java
try {
    int n = future.get(3, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    // Decide whether to retry, cancel, or close the channel per contract.
}
~~~

This snippet uses an existing `Future<Integer> future` and imports `TimeoutException` and `TimeUnit`. **A timeout on `get` is a timeout on waiting for the result**, not a guarantee that I/O stopped immediately.

Some socket API overloads also allow configuring a timeout directly when executing asynchronous `read/write`; check the specific overload's API contract instead of applying `Future.get` timeout semantics to every channel.

### 12.2. Cancellation Does Not Mean Rollback

If you call:

~~~java
boolean cancelled = future.cancel(true);
~~~

successfully canceling the Future **does not mean previously written bytes are undone**. The I/O operation may have partially transferred data before cancellation, or the channel may have to be closed depending on the case/implementation.

Avoid reading or reusing the buffer immediately after a cancellation request unless you are certain the previous task has ended its access. Safer options are waiting for completion confirmation, enforcing strict ownership, or closing and discarding the channel/buffer under a resource-management policy.

### 12.3. Closing the Channel

A channel may close while I/O operations are still waiting; those requests may fail. In a program handling many requests, ensure **every request has a terminal state**: success, error, cancellation, or timeout. Do not let a failed callback drop its signal and leave a caller waiting forever.

`try-with-resources` works well when the I/O lifecycle is scoped to a single block; however, with callbacks, **do not close the channel right after registering a callback** if it is still needed for completion. Keep the channel alive until the required operations complete or are canceled in a controlled manner.

## 13. Common Mistakes and How to Fix Them

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Calling `Future.get()` directly on the event-loop/UI thread | Blocks the critical thread | Move waiting to a suitable worker or use callbacks |
| Assuming `future.isDone() == true` means success | Misses errors/cancellations | Call `get()` or inspect state and handle exceptions |
| Ignoring `ExecutionException.getCause()` | Hides the I/O root cause | Log and classify the underlying cause |
| Swallowing `InterruptedException` | Loses stop signal | Restore interrupt or propagate per policy |
| Assuming one `read/write` transfers all bytes | Lost data or incomplete writes | Use the actual byte count to continue |
| Reading a buffer before I/O completes | Unstable data/indices | Keep ownership with the running operation |
| Sharing one buffer across parallel I/O | `position/limit` races | Use separate buffers or queue operations |
| Forgetting `failed(...)` | Request hangs forever | Terminate the request with an error state |
| Closing the channel right after `read(..., handler)` | Running I/O fails | Keep the channel alive across the operation lifecycle |
| Running long CPU-bound/blocking work in callbacks | Degrades other I/O handling | Offload work to an appropriate executor |
| Retrying continuously when `n == 0` | Busy-spin, wastes CPU | Wait for proper condition or fail fast intentionally |
| Confusing `get(timeout)` with I/O cancellation | Task still uses the buffer | Handle cancellation/closing/lifecycle separately |
| Calling `read` twice concurrently on the same async socket | `ReadPendingException` | Build a sequential read loop |
| Relying on callbacks completing in submission order | Business ordering bugs | Attach request IDs and coordinate ordering |

## 14. Choosing `Future` or `CompletionHandler`?

**Choose `Future`** when you want readable control flow, have workers permitted to wait, or need timeouts on waiting. For example, a batch job processing several independent files: initiate multiple operations on separate buffers, do other work, and collect results when needed.

**Choose `CompletionHandler`** when many concurrent I/O operations are needed and you want immediate notification when an operation completes, fitting pipelines, socket servers, or event-driven task chains. You must manage callback state and load limits.

**Combining `CompletionHandler` with `CompletableFuture`** is a useful way to turn callbacks into a composable result representation. The example above shows a single `CompletableFuture` representing **the entire full-read process**, even though the underlying operations occur across multiple callbacks.

The choice also depends on libraries, executor architecture, concurrent connection/file counts, latency requirements, error handling, and testability. **Neither API automatically makes I/O faster purely through its result-notification style**.

## 15. Self-Check Questions

**Question 1.** `Future<Integer> f = channel.read(buffer, 0)` just returned. Is the data in `buffer` ready to process?

**Answer:** You cannot conclude that. You must wait for/verify operation completion, check the result, and only then use the buffer.

**Question 2.** `f.get()` throws `ExecutionException`. Did the I/O succeed or fail?

**Answer:** The operation failed; inspect `getCause()` for the reason. `Future.isDone()` may still return `true`.

**Question 3.** An asynchronous call writes 10 bytes, yet the callback receives `completed(4, attachment)`. Can it be considered fully written?

**Answer:** Not yet. 4 bytes were transferred; keep the remaining 6 bytes and continue using the actual position/buffer state.

**Question 4.** Reading through `AsynchronousFileChannel` returns `-1` while the buffer still needs 5 more bytes. What does this mean?

**Answer:** EOF before reaching the expected data. If the protocol/requirement demands those exact 5 missing bytes, this is an incomplete-data error.

**Question 5.** Calling `get(1, SECONDS)` throws `TimeoutException`. Can you immediately modify the `ByteBuffer` passed to that I/O?

**Answer:** Not by default. The timeout only ends waiting; the I/O may still be running and using the buffer.

**Question 6.** Can you call another `read(...)` on an `AsynchronousSocketChannel` that already has a pending read?

**Answer:** No; you may hit `ReadPendingException`. You must chain reads sequentially after each completion.

**Question 7.** Why does the handler have an `attachment` parameter?

**Answer:** So the callback receives context tied to the operation—such as offset, request id, or state—without relying on shared global variables.

**Question 8.** If the `failed(...)` callback only logs without completing the coordinating Promise/Future, what happens?

**Answer:** The waiting component may hang indefinitely. The error path must also publish a terminal state.

## 16. Key Takeaways

- **`Future`:** receives an object representing the result; `get()` can block the waiter, execution errors arrive in `ExecutionException`; a wait timeout does not automatically stop I/O.
- **`CompletionHandler`:** delivers results/errors via `completed(...)` and `failed(...)`; attachments carry context; callbacks should be brief, control state, and report errors.
- **Asynchronous I/O still has partial I/O**: continue according to the returned byte count; never assume one call is enough.
- **Buffers have ownership while I/O is running**; do not reuse or mutate buffers before completion.
- **Asynchronous sockets** must coordinate pending operations, framing, backpressure, and connection lifecycles.
- **A correct solution** provides an explicit terminal state for every operation: success, failure, timeout, or controlled cancellation.
