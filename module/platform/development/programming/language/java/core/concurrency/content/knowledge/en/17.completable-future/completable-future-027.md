# NIO CompletionHandler: Bridging completed()/failed() Callbacks to CompletionStage

## 1. Objectives and Context

Asynchronous NIO.2 APIs in Java (since Java 7), such as `AsynchronousFileChannel` and `AsynchronousSocketChannel`, provide overloads that accept a `CompletionHandler<V, A>`. When an operation finishes, the library invokes `completed(V result, A attachment)`; when it fails, the library invokes `failed(Throwable exc, A attachment)`. This model works well for individual I/O calls, but when multiple steps are chained together, nested callbacks make the success path, error handling, and resource cleanup hard to follow.

`CompletionStage<T>` (Java 8+) represents a future result and enables step composition with `thenApply`, `thenCompose`, `thenCombine`, `handle`, `exceptionally`, and `whenComplete`. `CompletableFuture<T>` is an implementation that both provides the mechanism to complete a result and implements `CompletionStage<T>`.

**Scope:** Bridging pure Java NIO callbacks into stages, covering completion points, errors, partial data, channel management, cancellation, and timeouts. This is a general Java concurrency mechanism; no Spring or external framework is required.

After this lesson, you should be able to:

- Identify accurately when to complete a stage with a value and when to complete it exceptionally.
- Write an adapter from `CompletionHandler` to `CompletableFuture` and expose `CompletionStage`.
- Use stages to chain operations, recover from errors, and coordinate multiple operations.
- Handle byte counts, EOF, and the lifecycle of `ByteBuffer` and channels properly; avoid confusing the completion of a single read with the completion of an entire message.
- Understand the boundary between stage cancellation/timeout and actual I/O cancellation.

## 2. Understanding the CompletionHandler Contract

~~~java
public interface CompletionHandler<V, A> {
    void completed(V result, A attachment);
    void failed(Throwable exc, A attachment);
}
~~~

The two type parameters have distinct meanings:

| Component | Meaning | Example |
| --- | --- | --- |
| `V` | Result of **a single I/O operation** | `Integer`: number of bytes read/written; `Void`: connection succeeded |
| `A` | Attachment passed by the **caller** to carry context across the callback | A request/context object, or `Void` when unused |
| `completed(result, attachment)` | The operation completed normally | Do not assume all application-level data has been read |
| `failed(error, attachment)` | The I/O operation completed with an error | May be caused by a closed channel, broken connection, access permissions, etc. |

Common method signatures (simplified):

~~~java
// AsynchronousFileChannel
<A> void read(
    ByteBuffer dst, long position, A attachment,
    CompletionHandler<Integer, ? super A> handler);

// AsynchronousSocketChannel
<A> void connect(
    SocketAddress remote, A attachment,
    CompletionHandler<Void, ? super A> handler);

<A> void read(
    ByteBuffer dst, A attachment,
    CompletionHandler<Integer, ? super A> handler);
~~~

For `read`, `completed(n, …)` reports **n bytes from that single read**, not necessarily the entire file or the entire message. A value of `-1` indicates end-of-stream (EOF); `0` does not mean EOF. Because `ByteBuffer` has its `position` updated during the read, you must call `flip()` before reading data out of it and `clear()`/`compact()` before the next read.

In particular, errors can occur at **two different points**: (1) synchronously when invoking the method that initiates I/O, such as invalid arguments or an already pending operation of the same type; (2) later inside `failed()`. The adapter must handle both paths.

## 3. Rules for Bridging Callbacks to Stages

The basic mapping is:

| NIO Signal | Effect on `CompletableFuture<T>` |
| --- | --- |
| `completed(value, attachment)` | `future.complete(value)` |
| `failed(error, attachment)` | `future.completeExceptionally(error)` |
| I/O initiation call throws a synchronous exception | `future.completeExceptionally(error)` |
| `read` result equals `-1` | Handle EOF according to the **adapter's** protocol before completing the stage |

A concise adapter for **a single completion callback**, without channel/timeout management yet:

~~~java
import java.nio.channels.CompletionHandler;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.function.Consumer;

static <T> CompletionStage<T> fromCallback(
        Consumer<CompletionHandler<T, Void>> register) {
    CompletableFuture<T> promise = new CompletableFuture<>();

    CompletionHandler<T, Void> handler = new CompletionHandler<>() {
        @Override
        public void completed(T value, Void ignored) {
            promise.complete(value);
        }

        @Override
        public void failed(Throwable error, Void ignored) {
            promise.completeExceptionally(error);
        }
    };

    try {
        register.accept(handler);
    } catch (RuntimeException startError) {
        promise.completeExceptionally(startError);
    }

    return promise;
}
~~~

Here `register` accepts the callback and registers the I/O operation. The return type is `CompletionStage<T>` so the calling layer focuses on stage composition. `CompletableFuture` remains internal so the adapter controls completion. `complete`/`completeExceptionally` succeeds only on the first completion; subsequent completion attempts return `false`. This is helpful when races occur, though it does not replace proper resource management.

Example of using this adapter for a single read on an open socket:

~~~java
// Example snippet placed in a class containing fromCallback above.
// channel: connected AsynchronousSocketChannel
// dst: ByteBuffer with remaining capacity to receive data
CompletionStage<Integer> oneRead =
    fromCallback(handler -> channel.read(dst, null, handler));
~~~

The `oneRead` stage carries only **the byte count of a single read**. If the application needs a line, a fixed-length frame, or a complete file, it must continue reading and accumulating data according to the protocol before completing the application-level stage.

## 4. Runnable Java 17+ Example: Reading an Entire NIO File and Returning CompletionStage<String>

This example creates a UTF-8 file, opens it with `AsynchronousFileChannel`, reads chunks until EOF, accumulates bytes before UTF-8 decoding, closes the channel, and completes the stage. Error paths during open, read submission, and callback are all converted into exceptional completion. Decoding **after collecting all bytes** avoids splitting a multi-byte UTF-8 character across chunk boundaries.

Save as `CompletionHandlerBridgeDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class CompletionHandlerBridgeDemo {
    static CompletionStage<String> readUtf8(Path path) {
        final AsynchronousFileChannel channel;
        try {
            channel = AsynchronousFileChannel.open(
                path, StandardOpenOption.READ);
        } catch (IOException | SecurityException error) {
            return CompletableFuture.failedFuture(error);
        }

        CompletableFuture<String> result = new CompletableFuture<>();
        ByteBuffer buffer = ByteBuffer.allocate(1024);
        ByteArrayOutputStream data = new ByteArrayOutputStream();

        class ReadLoop implements CompletionHandler<Integer, Void> {
            private long position;

            void submit() {
                try {
                    channel.read(buffer, position, null, this);
                } catch (RuntimeException error) {
                    finish(null, error);
                }
            }

            @Override
            public void completed(Integer count, Void ignored) {
                if (count == -1) {
                    finish(new String(
                        data.toByteArray(), StandardCharsets.UTF_8), null);
                    return;
                }

                if (count > 0) {
                    position += count;
                    buffer.flip();
                    byte[] chunk = new byte[buffer.remaining()];
                    buffer.get(chunk);
                    data.write(chunk, 0, chunk.length);
                    buffer.clear();
                }

                // count == 0: not EOF yet, try again.
                submit();
            }

            @Override
            public void failed(Throwable error, Void ignored) {
                finish(null, error);
            }

            private void finish(String value, Throwable failure) {
                try {
                    channel.close();
                } catch (IOException closeError) {
                    if (failure == null) {
                        failure = closeError;
                    } else {
                        failure.addSuppressed(closeError);
                    }
                }

                if (failure == null) {
                    result.complete(value);
                } else {
                    result.completeExceptionally(failure);
                }
            }
        }

        new ReadLoop().submit();
        return result;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("nio-demo-", ".txt");
        Path missing = Files.createTempFile("nio-missing-", ".txt");
        Files.delete(missing);

        try {
            Files.writeString(
                file, "Xin chào NIO", StandardCharsets.UTF_8);

            String upper = readUtf8(file)
                .thenApply(s -> s.toUpperCase(Locale.ROOT))
                .toCompletableFuture()
                .join();
            System.out.println(upper);

            String fallback = readUtf8(missing)
                .exceptionally(error -> "Không đọc được")
                .toCompletableFuture()
                .join();
            System.out.println(fallback);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac -encoding UTF-8 CompletionHandlerBridgeDemo.java
java CompletionHandlerBridgeDemo
~~~

Stdout on normal execution:

~~~text
XIN CHÀO NIO
Không đọc được
~~~

Key points breakdown:

1. **Opening the channel:** An error occurring immediately at `open` becomes `CompletableFuture.failedFuture(error)`; the caller still receives a failed stage instead of needing two separate error-handling mechanisms.
2. **Initiating I/O:** `submit` calls `read(buffer, position, null, this)`. `this` is the `CompletionHandler<Integer, Void>` of the read loop itself. Synchronous exceptions from the submission call are routed into `finish`.
3. **Partial reads:** Only when `count > 0` do we advance the offset and copy data into `ByteArrayOutputStream`. After `flip()` and extracting the bytes, `clear()` prepares the buffer for the next read. When `count == 0`, the offset is not incremented and the loop submits another read.
4. **EOF:** `count == -1` means no more bytes remain to be read. Only at this point do we decode all UTF-8 bytes and complete the **file-reading stage**.
5. **Asynchronous errors:** `failed(error, …)` goes through `finish(null, error)`. The stage transitions to failed; downstream `exceptionally`/`handle` operators can process it.
6. **Resource ownership:** Because the adapter **opens** the channel itself, it also **closes** it on either success or failure before completing the stage. If closing the channel fails, the example preserves the close error as the primary failure when no prior failure occurred, or attaches it to the original failure via `addSuppressed`.
7. **Composition:** `thenApply` uppercases the read content; `exceptionally` recovers from the missing-file error with a fallback value. `join()` appears only in `main` so the demo waits for results; I/O callbacks never block synchronously.

This code is intended for small files with single ownership of the channel: `ByteArrayOutputStream` holds **all** data in RAM. For large files, enforce a size limit, write to a sink/stream, or design a chunk-based consumer. If the file is modified while being read, the observed data may not be a consistent snapshot. Asynchronous `read` does not guarantee that the OS layer performs file I/O completely without blocking threads; the implementation may rely on a thread pool.

## 5. Bridging Other Operations: connect, read, write

### Connect: completed(Void) to CompletionStage<Void>

`AsynchronousSocketChannel.connect` uses a `Void` result. A successful connection completes the stage with `null`; there is no need to substitute a dummy value such as `true`.

~~~java
// Placed in the same class as the fromCallback method in section 3.
// Add import java.net.SocketAddress;
// and import java.nio.channels.AsynchronousSocketChannel;
static CompletionStage<Void> connectStage(
        AsynchronousSocketChannel channel, SocketAddress remote) {
    return fromCallback(handler ->
        channel.connect(remote, null, handler));
}
~~~

In this example, the **caller** creates and owns the socket; the `connectStage` adapter does not close the socket after connecting because subsequent reads/writes are needed. If connecting fails, the socket-owning layer must decide to close and release it.

### Socket read: CompletionStage<Integer> is not a complete message

~~~java
static CompletionStage<Integer> readOnce(
        AsynchronousSocketChannel channel, ByteBuffer dst) {
    return fromCallback(handler ->
        channel.read(dst, null, handler));
}
~~~

After `readOnce` succeeds, check `n`: `-1` is EOF on the read stream; a positive number is the count of newly received bytes, which may be only **part** of a frame or message. TCP transmits a byte stream without preserving message boundaries. Build a protocol: for example, a 4-byte length prefix + reading the full payload, or reading until a delimiter. Never treat a single `completed()` callback as "a complete request has been received."

### Socket write: account for partial writes

`AsynchronousSocketChannel.write` completes a single operation with the number of bytes actually written; bytes may still remain in `src` (check `src.hasRemaining()`). If the goal is to "send the entire message," chain `write` calls until the buffer is drained before calling `complete(null)` on the application-level stage. Avoid mutating or reusing the buffer while an operation is still in flight.

## 6. Composing Stages for Readable Processing Pipelines

Assume `connectStage` and `readOnce` are the two methods above and the socket is managed by the calling layer:

~~~java
// Illustrates a single read only; not yet a full message reader.
CompletionStage<Integer> pipeline =
    connectStage(channel, remote)
        .thenCompose(unused -> readOnce(channel, dst))
        .thenApply(n -> {
            if (n == -1) {
                throw new IllegalStateException("Peer đã đóng chiều đọc");
            }
            return n;
        });

pipeline.whenComplete((n, error) -> {
    if (error != null) {
        // Log and close the socket according to the ownership policy.
    } else {
        // n bytes received; flip and process the buffer here.
    }
});
~~~

Distinguishing the operators:

| Operator | When to use | Notes |
| --- | --- | --- |
| `thenApply(T -> U)` | Pure result transformation | If the callback throws an exception, the next stage fails |
| `thenCompose(T -> CompletionStage<U>)` | Next step is **asynchronous and dependent** on the previous one | "Flattens" the stage, avoiding nested stages |
| `thenCombine(other, (a,b) -> c)` | Combine two independent results | Both stages must complete normally to compute the result |
| `exceptionally(error -> T)` | Recover with a fallback value | Produces a normal stage if the recovery function succeeds |
| `handle((value,error) -> U)` | Map both success and failure | Do not use when you only want to observe |
| `whenComplete((value,error) -> …)` | Observe/log/cleanup | Typically preserves the incoming result or error if the action throws no new error |

A `thenApply` does not necessarily run on the thread that registered the stage: when upstream completes, dependent logic may execute directly on the thread calling `complete` (often the NIO completion thread). If the processing step is CPU-intensive, use `thenApplyAsync(fn, executor)` or `thenComposeAsync(fn, executor)` with an application-managed executor to avoid starving I/O completion workers. `Async` does not make I/O itself faster.

Never call `join()`/`get()` inside a channel callback to "wait for the next step"; blocking a callback thread can reduce throughput or cause deadlock if dependent tasks share the same executor.

## 7. Errors, Timeouts, and Cancellation: Three Distinct Concerns

### Exceptional completion

In the adapter, `failed(Throwable)` must use `completeExceptionally` so downstream receives the same failure cause. When calling `join()` on a failed stage, callers typically see a `CompletionException` wrapping the cause; `get()` uses `ExecutionException` and throws checked exceptions. For errors inside `thenApply`, the transformation itself also causes the next stage to fail. Do not silently turn all errors into an empty string or `null`, as that hides the root cause and disguises failure as success.

### Future timeout does not mean I/O cancellation

~~~java
// The read stage is created from the CompletableFuture returned by the adapter.
CompletableFuture<String> timed =
    readUtf8(path).toCompletableFuture()
        .orTimeout(2, java.util.concurrent.TimeUnit.SECONDS);
~~~

`orTimeout` (Java 9+) completes the associated `CompletableFuture` with a `TimeoutException` if it has not finished; in this example it acts on the future created by the adapter itself. **It does not instruct the channel to stop reading or close the channel.** If the NIO operation completes after the timeout, the callback's `complete(...)` call returns `false`. The adapter must still clean up resources when I/O actually finishes, or define an explicit I/O stopping policy.

`completeOnTimeout(fallback, …)` likewise completes the future with a fallback value when time expires; the in-flight I/O operation does not stop automatically. Closing a channel to force pending I/O to fail can affect **all** operations sharing that channel. Do not use one request's cancellation mechanism to close a socket shared by other requests without a clear ownership policy.

### Cancellation also does not propagate through CompletionHandler

`CompletableFuture.cancel(true)` normally marks the future as cancelled (completing with `CancellationException`); for `CompletableFuture`, the `mayInterruptIfRunning` parameter does not interrupt a thread executing an NIO operation. Unless the adapter registers a separate stop mechanism, cancelling the future **does not cancel the underlying NIO operation**. NIO APIs also provide overloads returning `Future<Integer>`: that is a different object, with channel/provider-specific cancellation behavior. Do not conflate the two APIs or assume `cancel()` on one object controls the other.

Decide the application's policy upfront: if you only discard late results, keep the channel alive until the callback arrives and clean up upon completion; if true I/O cancellation is required, use a mechanism supported by the API and assess its impact on operations sharing the channel. All resource-closing paths should be idempotent or guarded to ensure closing happens exactly once if multiple signals race.

## 8. Real-World Races and Pitfalls to Avoid

1. **Forgetting the failed path:** Implementing only `completed` causes the stage to hang indefinitely when NIO reports an error. Both submission exceptions and the `failed` callback must be handled.
2. **Confusing a single callback with complete data:** `read` can return fewer bytes than needed. Handle `-1`, `0`, partial reads/writes, and socket framing or file read loops.
3. **Reusing ByteBuffer too early:** Never write to, `clear`, or `flip` a buffer from another thread while pending I/O is still using it. After the callback, update `position`/`limit` properly.
4. **Closing the channel right when the adapter method returns:** With asynchronous I/O, wrapping only the initiation call in `try (channel)` and returning will close the channel **before the callback arrives**. Close after actual completion or delegate ownership to the caller.
5. **Unclear channel ownership:** An adapter that opens its own channel should close it; an adapter receiving a socket from the caller should not close it after a successful `readOnce`. Timeout/cancellation design also depends on that ownership.
6. **Dropping resource close errors:** If cleanup fails, record the error without overwriting the original I/O error. `addSuppressed` preserves both.
7. **Heavy work in callbacks:** Long CPU-bound blocks in a callback or synchronous `thenApply` can monopolize completion threads. Offload heavy work to an appropriate executor.
8. **Uncontrolled overlapping pending I/O:** Submitting overlapping reads on an `AsynchronousSocketChannel` can throw `ReadPendingException`; likewise `WritePendingException` for writes. Sequence reads/writes according to operation state.
9. **Mishandling timed-out or cancelled futures:** `complete` returns `false` if the stage has already finished, yet the callback can still arrive. Do not rely solely on future completion to decide channel cleanup.
10. **Assuming all completions run on a fixed thread:** Do not rely on thread ordering or a specific callback thread to protect state; keep only one read pending at a time, synchronize state as needed, and manage executors explicitly.

## 9. How to Verify Your Adapter

At a minimum, test the following scenarios when implementing an adapter for any NIO operation:

| Scenario | Expected Result |
| --- | --- |
| Valid `completed(value)` | Stage succeeds; downstream receives the exact value |
| `failed(cause)` | Stage completes exceptionally, preserving `cause` |
| API throws synchronously at initiation | Adapter returns an exceptional stage; no opened channel is leaked |
| A read returns only partial bytes | Continues reading until the application-level completion condition is met |
| Read returns `-1` | Terminates/marks EOF according to the protocol |
| UTF-8 data split across two chunks | Decodes accurately after assembling all bytes or using a stateful decoder |
| Timeout or caller cancellation before callback | No duplicate results; I/O and resources are handled per the chosen policy |
| Close error after an I/O error | Primary I/O error is preserved; close error appears in suppressed exceptions |

You can verify the complete code in section 4 with `javac`/`java`, then increase the file size beyond 1,024 bytes and include many Vietnamese characters to observe that the read loop still reassembles them accurately. For sockets, split a payload across multiple sends to see that a single `read` does not necessarily correspond to a single message. When testing timeouts/cancellation, use deterministic conditions rather than relying on OS timing luck.

## 10. Key Takeaways

`CompletionHandler` is the mechanism for **receiving completion signals from NIO**; `CompletableFuture` is the mechanism for **emitting success/error signals to the processing pipeline**; `CompletionStage` is the interface for **composing asynchronous steps**. A correct bridge starts with `complete`/`completeExceptionally`, but a production-usable adapter must also define **the unit of result** (a single read vs. an entire message), **when resources are closed**, **the synchronous error path**, and **the timeout/cancellation policy**.

Expose `CompletionStage<T>` when callers only need to compose; keep completion control inside the adapter. With NIO, always distinguish between **an operation having completed** and **the application-level task being finished**.
