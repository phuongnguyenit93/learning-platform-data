# Handling Errors, Interruptions, Timeouts, and Closing Channels in Asynchronous Java NIO

## 1. Why Does Asynchronous I/O Need Strict Lifecycle Management?

Java NIO.2 APIs such as `AsynchronousFileChannel`, `AsynchronousSocketChannel`, and `AsynchronousServerSocketChannel` let you start read/write/connect/accept and receive the result **later**, rather than forcing the calling thread to wait until the operation completes at the call site.

An operation may complete successfully, fail, be canceled, time out, or be affected by channel closure. You must distinguish **Future/callback status**, **the state of transferred bytes**, **ByteBuffer usage rights**, and **connection/file state**. These are not the same concept.

~~~text
Request -> submit async I/O -> PENDING
                                |   |    |
                                |   |    +-- cancel/timeout/close
                                |   +------- FAILED
                                +----------- COMPLETED
                                             |
                                       returns byte count
After each branch: classify, terminate request exactly once,
clean up channel/buffer/attachment according to ownership.
~~~

Do not equate "submitted a write request" with "finished writing all bytes," and do not equate "wait timeout" with "I/O has definitely stopped."

## 2. Future and CompletionHandler: Two Result-Delivery Models

### Future

~~~java
// Illustration: file is an AsynchronousFileChannel opened for reading.
ByteBuffer buffer = ByteBuffer.allocate(256);
Future<Integer> pending = file.read(buffer, 0L);

int n = pending.get(); // May wait until I/O finishes.
~~~

- `get()` waits and returns the bytes read/written; may throw `InterruptedException` or `ExecutionException`.
- `get(timeout, unit)` may additionally throw `TimeoutException` when the **caller** waits too long.
- `cancel(false/true)` attempts to cancel the computation; `isCancelled()` and `isDone()` report Future status.
- Do not reuse the ByteBuffer for another operation before having a safe completion/cancellation handling procedure.

The I/O call is asynchronous, yet `future.get()` can still **block the waiting thread**. This model is simple, though calling `get()` sequentially for each request can reduce concurrency.

### CompletionHandler

~~~java
// Illustration, not a standalone program.
file.read(buffer, 0L, "req-42",
        new CompletionHandler<Integer, String>() {
            @Override
            public void completed(Integer n, String requestId) {
                System.out.println(requestId + ": " + n);
            }

            @Override
            public void failed(Throwable error, String requestId) {
                System.err.println(requestId + ": " + error);
            }
        });
~~~

`CompletionHandler<V,A>` has two callbacks:

- `completed(V result, A attachment)`: completed successfully.
- `failed(Throwable exc, A attachment)`: completed with failure.

The attachment can carry a request ID, state, context, or coordinator object. Handlers are dispatched via the async channel's thread pool; in some immediate-completion cases, they may be invoked directly by the initiating thread if it belongs to the pool.

**Handlers should be short.** Do not block for long or run heavy CPU work inside the callback pool. Offload long tasks to a separate executor if needed.

### Submission Errors Differ from Completion Errors

An operation-initiating call can throw an error immediately: invalid arguments, unconnected channel, pending same-direction read/write, etc. If initiation succeeds and I/O fails later, the result arrives via `failed(...)` or `Future.get()`.

Simply wrapping `read(..., handler)` in try/catch **does not replace** implementing `failed(...)`.

## 3. Common Errors and How to Classify Them

| Case | Exception/Result | Commonly Appropriate Action |
|---|---|---|
| Future hits I/O error | `ExecutionException` from `get()` | Inspect `getCause()`, fail the request |
| Handler hits error | `failed(Throwable, attachment)` | Complete promise/state with failure |
| Caller awaiting Future interrupted | `InterruptedException` | Restore interrupt flag, consider canceling |
| Caller wait timed out | `TimeoutException` | Do not infer background I/O stopped |
| Future canceled | `CancellationException` on `get()` | Do not report success, avoid blind retries |
| Pending file I/O when channel closes | `AsynchronousCloseException` | Clean up pending request and resources |
| Channel already closed before call | `ClosedChannelException` or API-appropriate error | Do not submit new I/O |
| Socket not yet connected | `NotYetConnectedException` | Connect first |
| Socket already has a pending read | `ReadPendingException` | Do not submit overlapping reads |
| Socket already has a pending write | `WritePendingException` | Queue writes |
| Direct socket I/O timeout | `InterruptedByTimeoutException` | Consider discarding buffer/channel |
| Read reaches EOF | Value `-1` | Distinguish valid EOF from truncated frame |
| One read/write processed only partially | Fewer bytes than desired | Keep ByteBuffer position, continue properly |

**Do not catch all exceptions and retry indefinitely.** Timeouts, EOF, channel closure, and programming bugs do not share the same recovery policy.

## 4. Unwrapping `ExecutionException` and Handling Callback Errors

When using Future:

~~~java
// Illustration inside a method with variables and checked exceptions.
try {
    int n = pending.get();
    consume(n);
} catch (ExecutionException e) {
    Throwable root = e.getCause();
    if (root instanceof AsynchronousCloseException) {
        // Channel was closed while processing.
    } else if (root instanceof IOException) {
        // File or network I/O error.
    } else {
        // Other error: do not treat as success.
    }
}
~~~

`consume` is an application-defined method. Log the root cause, request ID, file offset or peer, operation type, known byte count, and channel state.

When using callbacks, handle errors directly in `failed(Throwable, attachment)`; do not rely on `ExecutionException` since callback overloads do not return a Future for that operation. If code inside a handler throws an exception itself, that is a bug in callback-handling logic; catch and route it to the appropriate promise/request state to avoid disrupting the dispatcher.

### Success Still Requires Checking the Byte Count

A single `read()` may read fewer bytes than expected; `-1` means EOF. A single `write()` may write only part of a buffer. Never treat `completed(3)` as "received the entire 10-byte frame."

## 5. `InterruptedException`: Interrupts the Waiter, Does Not Automatically Cancel I/O

Example:

~~~java
try {
    int n = pending.get();
    use(n);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    pending.cancel(false);
    // Transition request to canceled state per policy.
}
~~~

This is an illustrative snippet; `pending` and `use` are defined externally.

Points not to confuse:

1. `InterruptedException` here reports that **the thread waiting** on the Future was interrupted.
2. It **does not prove** background I/O stopped or zero bytes were transferred.
3. Usually restore the interrupt status with `Thread.currentThread().interrupt()` or propagate the exception upward.
4. If deciding to cancel, include `cancel(...)`/`close()` steps and a buffer ownership plan.
5. Do not `clear()` or reuse a pending operation's buffer just because the caller stopped waiting.

| Call | Primary Effect | Not Guaranteed |
|---|---|---|
| `thread.interrupt()` | Sets thread interrupt flag; waiting `get()` may throw `InterruptedException` | I/O rolled back |
| `future.cancel(false)` | Attempts to cancel Future without requesting task interrupt | No side effects occurred |
| `future.cancel(true)` | Attempts to cancel and may request interrupting the task | Immediate kernel I/O stop |
| `channel.close()` | Closes channel, affecting pending operations | Rolling back transferred bytes |

## 6. `Future.get(timeout)` Timeout Limits Only Wait Duration

~~~java
int n = pending.get(250, TimeUnit.MILLISECONDS);
~~~

If the deadline expires, the waiting thread receives `TimeoutException`, yet the background operation may still be running. Scenario:

~~~text
t0: file.read(...) starts
t1: Future.get(250ms) begins waiting
t2: caller receives TimeoutException
t3: background I/O may still continue and mutate ByteBuffer
t4: I/O eventually completes/fails on its own schedule
~~~

Therefore, do not return the buffer to a pool or reuse the same buffer for a new operation immediately at t2.

A handling pattern:

~~~java
// Illustration, file and pending already declared.
try {
    int n = pending.get(250, TimeUnit.MILLISECONDS);
    consume(n);
} catch (TimeoutException e) {
    boolean cancelled = pending.cancel(false); // Best effort.
    // Do not assume cancelled == true means zero bytes were written.
    // Mark request timed out; manage buffer/channel separately.
}
~~~

This is a bound for **the waiter**, not a direct I/O timeout inside `AsynchronousFileChannel.read/write`. File read/write overloads take offsets, not socket-style I/O timeout parameters.

## 7. `AsynchronousSocketChannel` Timeouts: Stronger Semantics, Higher Risk

Asynchronous sockets provide callback read/write overloads with a timeout parameter:

~~~java
// Illustration: socket is connected, dst is writable.
socket.read(dst,
        500, TimeUnit.MILLISECONDS,
        requestId,
        new CompletionHandler<Integer, String>() {
            @Override
            public void completed(Integer n, String id) {
                // I/O completed.
            }

            @Override
            public void failed(Throwable error, String id) {
                if (error instanceof InterruptedByTimeoutException) {
                    // Timeout directly in the read operation.
                }
                // Terminate request per policy.
            }
        });
~~~

According to Java 17 documentation:

- If a timeout occurs before I/O completes, the handler receives **`InterruptedByTimeoutException`**.
- If the implementation cannot guarantee no bytes were or will be read/written, the channel may be placed into an **implementation-specific error state**. Subsequent reads/writes in the same direction may throw unspecified runtime exceptions.
- **The state of the ByteBuffer or buffer array after an I/O timeout is undefined.**
- Timeout values **less than or equal to 0** mean the operation does not time out (not an immediate poll).

**Common safe approach:** treat the request/connection as untrustworthy upon a socket timeout with unclear byte counts, close the channel, and do not reuse the associated buffer. If a retry is needed, open a new connection and use a request ID/idempotency key to prevent duplicate processing.

### Direct Comparison

| Mechanism | Exception | What Is Known on Timeout |
|---|---|---|
| `Future.get(500, MILLISECONDS)` | `TimeoutException` | Caller wait expired; I/O may still be running |
| `socket.read(dst,500,MILLISECONDS,att,handler)` | `InterruptedByTimeoutException` in `failed` | I/O timed out, ByteBuffer undefined, channel may be errored |
| Overall business deadline | Application-layer dependent | Still requires deciding cancel, close, retry |

`AsynchronousSocketChannel.connect(...)` has Future and callback overloads, but not the same timeout overloads as read/write; connect deadlines are usually managed by the coordination layer.

## 8. Canceling a Future Does Not Mean Rollback

`future.cancel(mayInterruptIfRunning)` attempts to transition the Future to the canceled state. If cancellation succeeds, `isCancelled()` is true and `get()` may throw `CancellationException`.

However, `cancel(true)` or `cancel(false)` **is not a transactional rollback**:

- Some bytes may already have been read/written by the OS before cancellation.
- The peer may already have processed the request even if the caller never received the result.
- `ByteBuffer.position()` is not sufficient evidence of protocol state after cancellation.
- Never retry a remote state-mutating command without idempotency or version checks.
- If you cannot confirm I/O has stopped and the buffer is safe, isolate or discard the buffer rather than reusing it immediately.

Bottom line: **cancel manages an operation's lifecycle, not data undo**.

## 9. Closing a Channel While Operations Are Pending

`AsynchronousFileChannel.close()` can be called at any time. Under the Java 17 contract, outstanding operations on the channel complete with **`AsynchronousCloseException`**.

~~~java
// Illustration: file is an AsynchronousFileChannel.
Future<Integer> op = file.read(dst, 0L);

// Another thread may call:
file.close();

// The thread calling get() must handle ExecutionException
// whose cause is AsynchronousCloseException.
~~~

Closing a channel does not guarantee transferred bytes are undone. Even if `isOpen()` returns true at one instant, another thread can close it immediately afterward: check-then-call I/O **does not eliminate races**.

### Controlled Shutdown Sequence

~~~text
OPEN -> CLOSING -> CLOSED
          |
          +-- stop accepting new requests
          +-- mark pending operations
          +-- wait with deadline for essential operations
          +-- cancel/close remaining operations
          +-- clean up callbacks, buffers, attachments
          +-- shut down owned pool/group
~~~

Design requests with states CREATED → PENDING → COMPLETED/FAILED/CANCELLED → CLEANED so each request receives an outcome **exactly once**. If a callback receives `AsynchronousCloseException` due to intentional shutdown, that may be an **expected** error; do not report success, yet it need not be treated as a system crash.

### Who Owns Which Resource?

| Resource | Proper Closing |
|---|---|
| `AsynchronousFileChannel` | `close()` or try-with-resources |
| `AsynchronousSocketChannel` | `close()` when request/connection finishes or errors |
| `AsynchronousServerSocketChannel` | `close()` to stop accepting |
| Dedicated `ExecutorService` for async files | `shutdown()`, `awaitTermination(...)`; `shutdownNow()` when needed |
| Dedicated `AsynchronousChannelGroup` for async sockets | `shutdown()` / `shutdownNow()` / `awaitTermination(...)` |

In **Java 17**, `ExecutorService` is not `AutoCloseable`; shut it down explicitly rather than putting an executor into try-with-resources. Never let a single request shut down a pool or group shared across multiple components.

`AsynchronousSocketChannel.shutdownInput()` / `shutdownOutput()` perform protocol-level half-close, **not replacing** closing the entire channel when a connection hits a severe state error.

## 10. ByteBuffer Ownership, Partial I/O, and Concurrency

Buffers passed into asynchronous operations **are not safe if the application concurrently modifies** `position`, `limit`, or contents before completion. Do not do this:

~~~java
// Wrong: the same ByteBuffer may still be used by the background read.
ByteBuffer dst = ByteBuffer.allocate(1024);
Future<Integer> first = file.read(dst, 0L);
dst.clear();
Future<Integer> second = file.read(dst, 1024L);
~~~

Although `AsynchronousFileChannel` allows multiple outstanding I/O operations, I/O ordering and callback ordering are not guaranteed when concurrent. Using the same buffer across multiple pending operations is unsafe. If multiple writes hit the same offset, the final content does not follow submission order automatically.

### Async Sockets Permit Only One Pending Read and One Pending Write at a Time

On a single `AsynchronousSocketChannel`, one read and one write can wait concurrently, however:

- Second read while previous read is pending → `ReadPendingException`.
- Second write while previous write is pending → `WritePendingException`.

Maintain send/receive queues and submit the next same-direction I/O only after the previous operation finishes. Do not catch the exception and spin-retry.

### One Completion Does Not Guarantee Transferring the Full ByteBuffer

If bytes remain in the buffer after read/write, further operations may be needed. File write example:

~~~java
// Illustration: AsynchronousFileChannel file, src, and offset already defined.
while (src.hasRemaining()) {
    Future<Integer> op = file.write(src, offset);
    int n = op.get();
    if (n <= 0) {
        throw new IOException("No write progress");
    }
    offset += n;
}
~~~

Do not submit the next write on the same buffer before the previous Future finishes. When read returns `-1`, that means EOF; if exactly N bytes are required, EOF before N is a truncated frame/record.

## 11. Complete Java 17+ Program: Future, Callback, and Close

This example needs no network server. It creates a temporary file, uses `AsynchronousFileChannel`, writes the ASCII string `ABC` via Future, reads it back via `CompletionHandler`, closes the channel, shuts down the executor, and cleans up the file.

Save as **`AsyncIoLifecycleDemo.java`**:

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
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class AsyncIoLifecycleDemo {

    private static int await(Future<Integer> future)
            throws InterruptedException, ExecutionException,
                   TimeoutException {
        try {
            return future.get(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            future.cancel(false);
            throw e;
        } catch (TimeoutException e) {
            future.cancel(false);
            throw e;
        }
    }

    private static int writeAll(
            AsynchronousFileChannel channel, ByteBuffer src)
            throws Exception {
        long offset = 0;
        int total = 0;

        while (src.hasRemaining()) {
            Future<Integer> op = channel.write(src, offset);
            int n = await(op);
            if (n <= 0) {
                throw new IOException("No write progress");
            }
            total += n;
            offset += n;
        }
        return total;
    }

    private static CompletableFuture<String> readAll(
            AsynchronousFileChannel channel, int expectedBytes) {
        ByteBuffer dst = ByteBuffer.allocate(expectedBytes);
        CompletableFuture<String> result = new CompletableFuture<>();

        class Reader implements CompletionHandler<Integer, Void> {
            private long offset = 0;

            void start() {
                channel.read(dst, offset, null, this);
            }

            @Override
            public void completed(Integer n, Void attachment) {
                if (n < 0) {
                    result.completeExceptionally(
                            new EOFException("Truncated file"));
                    return;
                }
                if (n == 0) {
                    result.completeExceptionally(
                            new IOException("No read progress"));
                    return;
                }

                offset += n;
                if (dst.hasRemaining()) {
                    try {
                        channel.read(dst, offset, null, this);
                    } catch (RuntimeException e) {
                        result.completeExceptionally(e);
                    }
                    return;
                }

                dst.flip();
                byte[] bytes = new byte[dst.remaining()];
                dst.get(bytes);
                result.complete(new String(
                        bytes, StandardCharsets.US_ASCII));
            }

            @Override
            public void failed(Throwable error, Void attachment) {
                result.completeExceptionally(error);
            }
        }

        try {
            new Reader().start();
        } catch (RuntimeException e) {
            result.completeExceptionally(e);
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("async-io-demo-", ".bin");
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            AsynchronousFileChannel channel =
                    AsynchronousFileChannel.open(
                            file,
                            Set.of(StandardOpenOption.READ,
                                   StandardOpenOption.WRITE),
                            pool);

            try (channel) {
                ByteBuffer out = ByteBuffer.wrap(
                        "ABC".getBytes(StandardCharsets.US_ASCII));
                System.out.println(
                        "future-write=" + writeAll(channel, out));

                CompletableFuture<String> read =
                        readAll(channel, 3);
                System.out.println(
                        "callback-read=" + read.get(5, TimeUnit.SECONDS));

                System.out.println("open=" + channel.isOpen());
            }

            System.out.println("closed=" + !channel.isOpen());
        } finally {
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            } finally {
                Files.deleteIfExists(file);
            }
        }
    }
}
~~~

Compile and run from the directory containing the source file:

~~~bash
javac AsyncIoLifecycleDemo.java
java AsyncIoLifecycleDemo
~~~

**Expected stdout when I/O succeeds without interruption/timeout:**

~~~text
future-write=3
callback-read=ABC
open=true
closed=true
~~~

Explanation:

1. `writeAll` writes until the source buffer has no remaining bytes. It does not assume a single write always writes all three bytes and updates the offset after each completion.
2. `readAll` initiates a read callback; if only a portion arrives, it continues at the next offset. Premature EOF or errors complete the `CompletableFuture` exceptionally.
3. `read.get(5,SECONDS)` lets the main thread wait for the actual callback result. Using `Thread.sleep(...)` to guess whether the callback has run is unreliable.
4. `isOpen()` is true before exiting try-with-resources. After `close()` is called automatically, `isOpen()` is false.
5. The program-owned executor is shut down after the channel closes, and then the temporary file is deleted.

If a timeout occurs while awaiting the callback, try-with-resources closes the channel before cleanup; this **does not mean rolling back** an operation that already transferred bytes. The example has a deterministic success path instead of trying to induce races with sleeps.

## 12. Responsible Future Timeout and Interrupt Pattern

~~~java
// Illustration: file is an AsynchronousFileChannel,
// dst belongs solely to this operation.
Future<Integer> op = file.read(dst, 0L);

try {
    int n = op.get(200, TimeUnit.MILLISECONDS);
    consume(n);
} catch (TimeoutException e) {
    op.cancel(false);
    // Do not reuse dst immediately.
    // Owner decides whether to close/isolate channel or clean up.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    op.cancel(false);
} catch (ExecutionException e) {
    logFailure(e.getCause());
}
~~~

`consume` and `logFailure` are application-defined methods. If `file` is a channel **shared across multiple requests**, do not close the entire channel just because one request timed out unless policy allows impacting all related requests. Lifecycle and ownership must be clear from the start.

## 13. Socket Timeout Pattern with CompletionHandler

~~~java
// Illustration: socket is connected; RequestContext is application-created.
socket.read(dst, 500, TimeUnit.MILLISECONDS,
        context,
        new CompletionHandler<Integer, RequestContext>() {
            @Override
            public void completed(Integer n, RequestContext ctx) {
                if (n < 0) {
                    ctx.peerClosed();
                } else {
                    ctx.readCompleted(n);
                }
            }

            @Override
            public void failed(Throwable error, RequestContext ctx) {
                ctx.failed(error);
                // For InterruptedByTimeoutException:
                // do not rely on prior buffer/channel state.
            }
        });
~~~

This snippet is not standalone; `RequestContext` and `ctx.*` are application-defined structures. Callbacks must ensure a request is reported succeeded/failed **once**, and shutdown must not race with callbacks to clean up the same buffer twice.

## 14. Thread Pools, AsynchronousChannelGroup, and Shutdown

`AsynchronousFileChannel.open(...)` can take an `ExecutorService`. Asynchronous socket channels can use an `AsynchronousChannelGroup` to handle callbacks and associated I/O resources.

| API | Meaning |
|---|---|
| `ExecutorService.shutdown()` | Stops accepting new tasks; already-submitted tasks may continue |
| `ExecutorService.shutdownNow()` | Attempts to interrupt executing tasks, immediate stop not guaranteed |
| `ExecutorService.awaitTermination(...)` | Waits with timeout for the pool to terminate |
| `AsynchronousChannelGroup.shutdown()` | Initiates graceful shutdown per contract |
| `AsynchronousChannelGroup.shutdownNow()` | Attempts immediate shutdown, closing channels in the group |
| `AsynchronousChannelGroup.awaitTermination(...)` | Waits for group termination |

Do not block callbacks for long by calling `Future.get()` for other I/O that also depends on the same small pool: that easily causes **thread starvation**. Only the component that **owns** the group/pool should shut it down, avoiding breaking shared channels.

## 15. Production Application Checklist

1. Give every request explicit states: CREATED → PENDING → COMPLETED/FAILED/CANCELLED → CLEANED.
2. Access ByteBuffers only after the operation completes and ownership is validly returned.
3. Always handle partial reads/writes, EOF, and actual byte counts.
4. For Futures, inspect the root cause from `ExecutionException.getCause()`; for handlers, implement `failed(...)`.
5. Distinguish waiter timeouts, socket I/O timeouts, and overall business deadlines.
6. When catching `InterruptedException`, propagate it or restore the interrupt flag.
7. Cancel is not rollback; retries need versioning/idempotency when side effects exist.
8. For sockets, enforce at most one pending read and one pending write per direction per contract.
9. Stop accepting new requests before shutdown; close channels and resolve all pending callbacks/futures.
10. Never shut down a shared executor or group from an individual request.
11. Log request ID, operation, offset/peer, timeout, root cause, and cleanup state.
12. Test EOF, partial I/O, timeouts, interrupts, cancellation, closing while pending, and shutdown races.

## 16. Common Mental Misconceptions

| Misconception | Reality |
|---|---|
| "Async method returned means I/O is done" | Wait for Future or callback. |
| "`Future.get(timeout)` timing out stops I/O" | Only the waiter expired; background work may continue. |
| "Interrupting the waiting thread rolls back the operation" | No rollback occurs. |
| "`cancel(true)` guarantees zero bytes were written" | No such guarantee exists. |
| "Socket timeout leaves the buffer intact" | Buffer state is undefined. |
| "After socket timeout, always retry on the same channel" | Channel may be in an error state. |
| "Callbacks always run on the caller's thread" | Callbacks belong to the pool; direct dispatch happens only under specific conditions. |
| "Catching exceptions at submit time is enough" | Completion errors must be handled via Future/handler. |
| "Closing a channel undoes data" | Close is not a transaction rollback. |
| "Async file writes complete in submission order" | Ordering when concurrent is not promised. |
| "Async sockets allow multiple pending reads" | Can throw `ReadPendingException`. |
| "Buffers can be cleared before the callback" | Unsafe while pending. |
| "Java 17 ExecutorService auto-closes with try-with-resources" | No; shut it down explicitly. |

## 17. Self-Check

1. `get(100, MILLISECONDS)` throws `TimeoutException`; might the I/O still be running? **Possibly.**
2. Does `InterruptedException` confirm zero bytes were transferred? **No.**
3. How can you find the cause of a failed Future? **`ExecutionException.getCause()`.**
4. Where do callbacks report failure? **`CompletionHandler.failed(...)`.**
5. What exception does a direct socket I/O timeout report? **`InterruptedByTimeoutException`.**
6. Is buffer state guaranteed stable after a socket I/O timeout? **Undefined.**
7. Does canceling a Future perform a transactional rollback? **No.**
8. Does `AsynchronousFileChannel` have a shared file pointer? **No; per-operation offsets.**
9. Closing an async file during a pending read/write leads to which error? **`AsynchronousCloseException`.**
10. Submitting two pending reads on an async socket? **May throw `ReadPendingException`.**
11. Completion reports 2 bytes when 8 bytes are needed—is it finished? **Not yet.**
12. Should a single request shut down a shared executor? **No.**
13. Can a timed-out remote write request be blindly retried? **No; verification/idempotency is required.**

## 18. Official Java SE 17 Documentation

- [AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): Future, CompletionHandler, close, offsets, and ordering.
- [AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): I/O timeouts, pending limits, and buffer state.
- [CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): completed/failed.
- [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get, get(timeout), cancel.
- [AsynchronousChannelGroup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): lifecycle and shutdown.
- [AsynchronousCloseException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousCloseException.html): pending operations and close.
- [InterruptedByTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptedByTimeoutException.html): socket I/O timeout.
