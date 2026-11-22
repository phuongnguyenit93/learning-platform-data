# Deadlines, Operation Cancellation, and Channel State After Errors in Asynchronous Java NIO

## 1. A Timeout Does Not Mean I/O Has Stopped

In asynchronous Java NIO, when calling `AsynchronousSocketChannel.read(...)`, `write(...)`, or `connect(...)`, the call may **initiate the work and return immediately**, while I/O is still in progress. Results are typically received in one of two ways:

- **`Future<V>`**: call `get()` when you want to wait and receive the result, or check `isDone()`, `cancel(...)`.
- **`CompletionHandler<V,A>`**: receive the `completed(result, attachment)` or `failed(error, attachment)` callback after the operation finishes.

A serious mistake is calling `future.get(200, MILLISECONDS)`, catching `TimeoutException`, and assuming that **the read/write has been cancelled**, so you can reuse the `ByteBuffer` or immediately continue reading on the same channel. In reality, the timeout on `Future.get(timeout)` **only limits how long the thread waits for the result**; it does not automatically abort the underlying I/O. If an operation is still pending, reusing the buffer or initiating another operation in the same direction can cause races, `ReadPendingException`/`WritePendingException`, or data corruption.

With the overloads that accept a timeout **directly on `AsynchronousSocketChannel.read/write`**, when the timeout expires, the operation completes with `InterruptedByTimeoutException`. Yet even then, the Java 17 API warns that **the state of the channel/connection and buffer may no longer be guaranteed**, because the runtime does not necessarily know whether bytes have already been read/written or will continue to be transferred.

**Opening takeaway:** you must distinguish three independent questions:

1. *Has the caller's deadline expired?* — the thread/logic no longer wants to wait.
2. *Has the I/O operation actually finished or been cancelled?* — the state of the operation, callback/future.
3. *Is the channel still safe to continue using?* — an `isOpen()` flag does not prove everything remains consistent after an error.

This lesson belongs to the **Asynchronous I/O** section, focusing on deadlines, operation cancellation, and handling channels after encountering errors in Java 17+.

## 2. Lifecycle Model of an Asynchronous Operation

Treat each read/write operation as a logical object with a **state**, **deadline**, **dedicated buffer**, and **owner**:

```text
NEW -- initiate read/write/connect --> PENDING
                                     |
                   +-----------------+------------------+
                   |                 |                  |
                   v                 v                  v
              COMPLETED           FAILED            ABANDONED
             (has result)    (I/O error/timeout) (caller stops waiting)
                   |                 |                  |
                   v                 v                  v
           check byte count     determine recovery   I/O may still be running
           + process frame      /close channel       -> must manage lifetime
                                     |
                                     v
                         CANCEL_REQUESTED / CLOSED
```

This diagram is an **application coordination model**. `Future.cancel` does not guarantee that the operating system has stopped the I/O, so `ABANDONED` must not be equated with "successful cancellation at the transport layer." The `Future` result may be considered cancelled, but the underlying effect and channel consistency still depend on the implementation.

### 2.1. Three Different "Clocks"

| Deadline type | Where is it applied? | What actually happens when it expires? |
|---|---|---|
| **Wait timeout** | `future.get(200, MILLISECONDS)` | The waiting thread receives `TimeoutException`; **the operation may still be pending** |
| **I/O operation timeout** | `AsynchronousSocketChannel.read(dst, 200, MILLISECONDS, att, handler)` or the equivalent `write` overload | The `failed` callback is invoked with `InterruptedByTimeoutException` if the operation has not completed; the channel/buffer may be in an undefined state |
| **Business/request deadline** | Managed by the application/framework, such as a time budget from the start of a request | Must span multiple stages: connect, send, receive, process, retry; no single `Future.get` does this automatically |
| **Shutdown/drain deadline** | During server shutdown, waiting for in-flight requests | A lifecycle policy; upon expiration, bounded cleanup must run and uncertain outcomes may have to be accepted |

Do not confuse a **caller-computed timeout** with a **timeout enforced by the I/O API**. For example, `AsynchronousFileChannel.read(dst, position)` returns `Future<Integer>`; `get(timeout)` on this future also only limits waiting, and does not create a file read operation with an intrinsic deadline equivalent to the `read` overload of `AsynchronousSocketChannel`.

### 2.2. Using an Overall Deadline with a Monotonic Clock

If a request has a 2-second budget, do not set three separate 2-second timeouts for connect, write, and read and claim the total is at most 2 seconds. Each step could consume nearly that entire duration.

When managing deadlines within the same JVM, use `System.nanoTime()` to measure **elapsed time**; do not use `System.currentTimeMillis()` as the clock driving durations because wall-clock time can be adjusted. One calculation you can use is:

```java
// Illustrative code, valid duration without overflow.
long started = System.nanoTime();
long budgetNanos = TimeUnit.SECONDS.toNanos(2);

// Before each step:
long remaining = budgetNanos - (System.nanoTime() - started);
if (remaining <= 0) {
    // Business deadline has expired: stop waiting and move to cleanup.
}
```

If a timeout API measured in milliseconds requires a positive value, be careful with nano-to-milli rounding, overflow bounds, and never silently turn an expired deadline into an infinite wait time. With `AsynchronousSocketChannel`, a timeout **≤ 0** in the `read/write` overloads means **no timeout**; it does not mean "fail immediately."

## 3. Timeout on Future.get: Stops Waiting, Does NOT Stop the Operation

Suppose:

```java
// Illustrative code; channel is connected and under the caller's ownership.
ByteBuffer dst = ByteBuffer.allocate(1024);
Future<Integer> pendingRead = channel.read(dst);

try {
    int bytes = pendingRead.get(200, TimeUnit.MILLISECONDS);
    // Read the completed I/O result.
} catch (TimeoutException waitExpired) {
    // Only the waiting thread timed out; the read may STILL be running.
    // Do not clear/flip/read dst; do not immediately issue another read.
}
```

**What is `TimeoutException` from `Future.get(timeout)`?** It only states that the future did not have a result the thread could retrieve within the wait time. It **does not call `cancel`**, **does not close the channel**, **does not guarantee I/O has not read bytes**, and **does not prove the peer did not send data**.

When catching the exception, the application needs to decide on a clear policy:

- **Keep waiting on the same future** if business policy allows and the deadline has not expired. Do not issue another read while the first read has not finished.
- **Abandon + close the channel** if the request has expired and there is no longer a reason to keep the connection. Closing reclaims resources and wakes pending I/O according to channel semantics. This is usually the simplest, safest policy once the result is no longer needed.
- **Request cancellation** but do not treat the `Future.cancel` result as proof that the OS-level operation has stopped. Control buffer/channel ownership and do not proceed assuming "state is definitely clean."
- **Perform business reconciliation** if a command with side effects was sent before waiting for the response. Do not conclude the command was not processed merely because `get` timed out.

### 3.1. Other Failure Paths of `get()`

| Result of `Future.get` | Meaning | Basic handling |
|---|---|---|
| Returns `Integer n` | I/O completed; `n` may be a partial byte count or `-1` on EOF (for read) | Process `ByteBuffer`, framing, partial I/O/EOF according to contract |
| `TimeoutException` from `get(timeout)` | The caller waited past the timeout | The operation may still be pending; manage cleanup |
| `ExecutionException` | The operation completed exceptionally; the root cause is in `getCause()` | Classify the cause: socket/file/permission/close error |
| `CancellationException` | The Future is already in cancelled state | Do not infer that underlying I/O has not transferred bytes |
| `InterruptedException` | The waiting thread was interrupted | Preserve the interrupt flag with `Thread.currentThread().interrupt()` and follow the cancel/close policy |

**Specifically:** `InterruptedException` while waiting on `get` is different from `InterruptedByTimeoutException` on a timed I/O operation. Both containing the word *Interrupted* does not mean the mechanism is the same.

## 4. Timeout on AsynchronousSocketChannel.read/write: Can Leave the Channel Unusable

Java 17 provides the overloads:

```java
// Illustrative API signatures:
<A> void read(ByteBuffer dst, long timeout, TimeUnit unit,
              A attachment, CompletionHandler<Integer, ? super A> handler);

<A> void write(ByteBuffer src, long timeout, TimeUnit unit,
               A attachment, CompletionHandler<Integer, ? super A> handler);
```

These are **illustrative signatures**, not standalone Java code. Unlike `read(ByteBuffer)` which returns `Future<Integer>` without timeout parameters, the overloads above attach a deadline to the asynchronous operation itself.

When a positive timeout expires before I/O completes:

1. The operation finishes via the `failed` callback with **`InterruptedByTimeoutException`**.
2. According to the Java 17 documentation, a timeout **may leave the channel or underlying connection in an inconsistent state**. If the implementation cannot guarantee that bytes have not been or will not be read/written, it may put the channel into an **implementation-specific error state** for that I/O direction.
3. After a read timeout, a subsequent `read` **may throw an unspecified runtime exception**. The same applies to `write` after a write timeout.
4. **The state of the `ByteBuffer` or buffer sequence used for timed I/O is *undefined***. The documentation recommends discarding the buffer or not accessing it while the channel remains open; the easiest-to-control practical policy is to **close the channel and not reuse that buffer for another request**.

Important distinctions:

- `channel.isOpen()==true` only indicates that the channel **has not been closed** at the API level; it **does not prove** it can still read/write normally after a timeout.
- One direction may be in an error state; do not rely on writes succeeding to conclude that all reads will remain valid, or vice versa.
- The runtime is permitted to put the channel into a platform/provider-specific error state, so **do not design recovery around a specific runtime exception** after a timeout.
- Do not call `buffer.clear()` and return it to a pool as if it were certain no I/O is still touching that memory region.

### 4.1. Illustrating CompletionHandler with Timeout

```java
// Illustrative code placed inside a method with variables channel, dst
// and an application-defined closeQuietly(channel) helper.
channel.read(dst, 500, TimeUnit.MILLISECONDS, null,
        new CompletionHandler<Integer, Void>() {
            @Override
            public void completed(Integer count, Void ignored) {
                if (count == -1) {
                    closeQuietly(channel); // EOF
                    return;
                }
                // count may be fewer than the bytes of one message.
                handleBytes(count, dst);
            }

            @Override
            public void failed(Throwable error, Void ignored) {
                if (error instanceof InterruptedByTimeoutException) {
                    recordTimeout(error);
                } else {
                    recordFailure(error);
                }
                // Keep the policy simple: errored channel -> close,
                // do not reuse dst/return it to the pool when state is uncertain.
                closeQuietly(channel);
            }
        });
```

This snippet is illustrative, **not a standalone compilable class**: `handleBytes`, `recordTimeout`, `recordFailure`, and `closeQuietly` are application-defined methods. On successful completion, the application may inspect the buffer/position after the callback; it must not read/write the same buffer before completion. On failure due to timeout, do not assume the buffer's contents or position are still valid.

### 4.2. Do Not Use Timeout ≤ 0 to Represent an Expired Deadline

The `AsynchronousSocketChannel` documentation specifies that a timeout **≤ 0** in the timeout-accepting overloads means the operation has **no timeout**. If you clamp a negative `remainingNanos` to `0` and pass it to `read`, a request that should have terminated instead becomes an unbounded read.

Instead, check whether **the deadline has expired** and do not initiate new I/O when `remaining ≤ 0`. If time remains, pass an appropriate unit with a positive value; consider rounding and a minimum bound sufficient not to lose the deadline.

## 5. Future.cancel: Cancelling Future State Does Not Mean Rolling Back Bytes

`Future.cancel(boolean mayInterruptIfRunning)` is a **cancellation request**. According to `AsynchronousChannel` in Java 17, the ability to cancel underlying I/O is **implementation-specific**; there is no general guarantee that bytes have not been transferred or that the operation actually stopped the moment `cancel` returns.

### 5.1. `cancel(false)` vs. `cancel(true)`

| Operation | What can be observed | What must NOT be inferred |
|---|---|---|
| `future.cancel(false)` | If cancellation succeeds, `isCancelled()` becomes true; waiters receive `CancellationException` | Underlying read/write definitely transferred no bytes; buffer is safe to reuse |
| `future.cancel(true)` | May make a stronger request; the runtime **may close the channel** to interrupt the operation; waiters on the cancelled future receive `CancellationException` | The channel is guaranteed to always be closed or safe to reuse |
| `channel.close()` | The channel is closed; incomplete outstanding I/O finishes with an appropriate error such as `AsynchronousCloseException` | The remote application definitely has not processed the command before close |

The `mayInterruptIfRunning` parameter **is not a "rollback network write" option**. If the implementation cannot verify byte state after cancel, it may put the channel into an error state, causing subsequent similar operations to fail.

**Buffer risk:** After cancelling a read/write, the documentation advises discarding the `ByteBuffer`s used or being very careful not to access them while the channel remains open. From a resource-ownership perspective, do not immediately return an "abandoned" buffer to a pool.

### 5.2. A Verifiable Operational Rule

If a request's deadline expires while a read/write is still pending:

1. Mark the request as no longer accepting a final result (once only) in application state.
2. Do not initiate a new read/write in the same direction on that channel.
3. Request cancellation if policy uses it, **without expecting cancel to guarantee underlying I/O has stopped**.
4. Close the channel and release other resources after ownership is established, avoiding access to buffers whose state is uncertain.
5. If a command with side effects was sent, mark the **business outcome as unknown** and reconcile by request ID/idempotency rather than retrying blindly.

In some applications, you may choose not to cancel the future and instead **close the channel directly** when the overall deadline expires. This is a simpler cleanup path because you do not try to salvage a connection that is already in a questionable state.

### 5.3. Race Between Completion and Cancellation

Suppose I/O finishes just as a timer is about to cancel:

```text
Timer thread:      check deadline -> prepare cancel
Completion thread: operation completes -> success callback
Timer thread:      call cancel / close
Application:       may receive both the success signal and cleanup action close together
```

Therefore, request logic needs a **state machine or atomic terminal decision**:

- `PENDING -> SUCCEEDED` if the operation completes and the result is accepted while the request is still alive.
- `PENDING -> FAILED/TIMED_OUT/CANCELLED` if the timeout/error decision occurs first.
- Once a terminal state is established, a late callback only **cleans up/logs**, never overwriting the emitted decision and never sending a second response.

`AtomicBoolean.compareAndSet(false, true)` or `AtomicReference<State>` are useful tools for a one-time decision. However, ensuring a *single terminal callback* at the application layer does not turn a network operation into an exactly-once transaction.

## 6. Channel State After Encountering Each Type of Error

You cannot infer "asynchronous I/O throws an exception = channel is always closed." You must distinguish **error type**, **connection state**, and **cleanup decision**.

| Situation | What state might the channel be in? | Safe policy |
|---|---|---|
| `Future.get(timeout)` throws `TimeoutException` | Still open, operation may be pending | Do not touch the buffer; if abandoning the request, close the channel |
| `InterruptedByTimeoutException` from timed read/write | May be open but in an **inconsistent/error state**, buffer undefined | Close the channel; do not retry with the same buffer/connection as if nothing happened |
| `Future.cancel(false/true)` succeeds | Future cancelled; underlying I/O and channel depend on provider, may be errored or closed | Do not treat as rollback; avoid reuse and perform controlled cleanup |
| `AsynchronousCloseException` | Channel was closed while I/O was pending | Do not continue using the channel; handle close/cleanup |
| `ClosedChannelException` | Channel was already closed when attempting to initiate I/O | Create a new channel if reconnecting; check lifecycle |
| `ReadPendingException` / `WritePendingException` | An I/O in the same direction is already pending on `AsynchronousSocketChannel`; channel is not necessarily broken | Fix state/serialization; do not start a second read/write in the same direction before completion |
| `NotYetConnectedException` | Socket channel has not completed connect | Wait for connect to succeed or report error; do not use as connected |
| `ConnectionPendingException` | A connect operation is already in progress | Do not initiate a second connect on the same channel |
| `ExecutionException` with I/O cause | Operation completed with an error; specific cause depends on the I/O path | Classify the cause; typically close the errored socket and decide retry at the request layer |
| `CancellationException` from `get` | Future is marked cancelled | Unknown where bytes went; do not infer channel is healthy |
| EOF (read returns `-1`) | Peer ended its sending direction; does not mean all business requests succeeded | Handle protocol, partial data, and appropriate close/half-close |
| Read/write returns positive byte count less than expected | **Partial I/O success**, not an error | Maintain buffer/connection state, continue valid operations |

### 6.1. `isOpen()` Only Answers Part of the Question

`channel.isOpen()` tells you whether the channel has been closed; it **does not guarantee**:

- That `connect` succeeded.
- That no operation is still pending.
- That there is no error state from a prior timeout/cancel.
- That the peer is alive and ready to process data.
- That the application on the other end has committed the business action.

To reuse a channel after an error, you must first have **proof** that it is valid under the API contract. With `AsynchronousSocketChannel` after a read/write timeout or cancellation that leaves byte state unclear, **closing and creating a new connection** is a more practical policy than trying to recover the same connection.

### 6.2. One Read and One Write Can Run Concurrently

`AsynchronousSocketChannel` allows **one outstanding read and one outstanding write at the same time**, but **does not allow two outstanding reads or two outstanding writes**. Issuing another operation in the same direction while the previous one has not finished leads to `ReadPendingException` or `WritePendingException`. This error usually reflects a **bug in the I/O state machine**, not a sign to keep retrying blindly to test your luck.

When you need to write multiple chunks, chain writes on completion, update `ByteBuffer.position()`, and only start the next write pass under proper buffer ownership; do not let multiple callbacks concurrently share a mutable buffer.

### 6.3. Incomplete Connect and Failed Connect

`AsynchronousSocketChannel.connect(remote)` returns `Future<Void>`. If the caller's `get(timeout)` expires, connect may still be pending: **do not issue read/write as if already connected**. If the callback/future reports connect failed, the JDK specifies that the channel is closed; to reconnect, open a new channel. For a timeout where "the caller no longer wants to wait for connect," close the channel to avoid the connection completing unexpectedly later.

## 7. ByteBuffer Ownership in Asynchronous I/O

### 7.1. Do Not Access a Buffer While an Operation Is Incomplete

`ByteBuffer` has mutable `position`, `limit`, and backing data. While `AsynchronousSocketChannel.read(dst)` is still pending, the runtime may update `dst`'s position/data. If another thread calls `clear()`, `flip()`, `put()`, or returns the buffer to a pool in the meantime, a race and data corruption can occur.

```text
t0: client.read(buffer)         -> Future pending
t1: future.get(100ms) timeout -> ONLY waiting timed out
t2: application buffer.clear() -> WRONG: I/O may still be using buffer
t3: runtime receives bytes   -> writes into buffer unexpectedly
t4: another handler uses buffer -> data overwritten / corrupted frame
```

**Rule:** a buffer is **exclusively borrowed/held** for a single I/O operation until a valid completion point. When timeout/cancellation makes consistency uncertain, do not return the buffer to a pool based solely on `Future.isCancelled()`.

### 7.2. A Callback May Arrive on Another Thread

`CompletionHandler` is invoked by the runtime on a thread associated with the asynchronous channel group. Therefore, code inside the callback must safely handle:

- Updating state/buffers without racing with timers, API-calling threads, and other handlers.
- Not blocking for long in the callback; if heavy business logic is needed, hand off to a separate executor.
- Never sharing a `ByteBuffer` across two in-flight operations.
- Coordinating cleanup when the channel is closed or the request deadline expires.

Do not assume the callback always runs on the thread that called `read()`. And do not assume `close()` makes all callbacks disappear; outstanding operations may complete with failure, and the `failed` callback still needs to handle cleanup idempotently.

### 7.3. Partial Reads and Writes

For reads, the result `n` may be smaller than one frame; you need framing (length prefix/delimiter) and byte accumulation. For writes, the result `n` may be smaller than `src.remaining()` at the start; update state and issue the next operation to send the remainder. A single successful future completion **does not** prove the entire message was delivered or processed by the remote application.

With `AsynchronousFileChannel`, each read/write takes an explicit **file position**, and multiple operations may be outstanding concurrently; completion order is not guaranteed. Therefore, file channels require even clearer **buffer and range ownership**, avoiding two writes to the same file region without a synchronization protocol.

## 8. Runnable Java 17+ Example: Wait Times Out While Read Continues, Then Cancel the Next Read

The example below uses TCP loopback with `AsynchronousServerSocketChannel` and `AsynchronousSocketChannel`, requiring no Internet access or external dependencies beyond the JDK. It does not rely on `Thread.sleep` to simulate a timeout: the server **intentionally withholds data** until the client proves its wait timeout has expired.

**What this demonstrates:**

1. The client connects asynchronously and succeeds.
2. The client initiates a `Future<Integer>` read of one byte and calls `get(150ms)`. Because the server has neither sent data nor closed, **only the wait operation expires**.
3. The server sends byte `X`. **The original read Future** completes and returns `X`; it was not cancelled by the `get` timeout.
4. The client initiates a second read while the server stays open without sending anything, then calls `cancel(false)`. The Future reports cancelled, but the code **does not treat this as an underlying I/O rollback**.
5. The client closes the channel and does not reuse the buffer of the cancelled operation.

Create **`AsyncDeadlineCancelDemo.java`**:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class AsyncDeadlineCancelDemo {

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(
                                     InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            Future<AsynchronousSocketChannel> accept = listener.accept();

            InetSocketAddress address =
                    (InetSocketAddress) listener.getLocalAddress();
            client.connect(address).get(3, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel peer =
                         accept.get(3, TimeUnit.SECONDS)) {

                System.out.println("Connected: " + client.isOpen());

                ByteBuffer firstBuffer = ByteBuffer.allocate(1);
                Future<Integer> firstRead = client.read(firstBuffer);

                try {
                    firstRead.get(150, TimeUnit.MILLISECONDS);
                    throw new IllegalStateException(
                            "Read unexpectedly completed");
                } catch (TimeoutException expected) {
                    if (firstRead.isDone()) {
                        throw new IllegalStateException(
                                "Read ended unexpectedly");
                    }
                    System.out.println(
                            "Wait timeout: read still pending");
                }

                // Server sends AFTER the caller has already hit get() timeout.
                ByteBuffer outgoing =
                        ByteBuffer.wrap(new byte[] { (byte) 'X' });

                while (outgoing.hasRemaining()) {
                    int written = peer.write(outgoing)
                            .get(3, TimeUnit.SECONDS);
                    if (written <= 0) {
                        throw new IllegalStateException(
                                "No write progress");
                    }
                }

                int count = firstRead.get(3, TimeUnit.SECONDS);
                if (count != 1) {
                    throw new IllegalStateException(
                            "Expected exactly one byte");
                }
                firstBuffer.flip();

                System.out.println("Read after wait timeout: "
                        + (char) (firstBuffer.get() & 0xff));

                // Second read is pending because the server keeps the connection open
                // but does not send any further data.
                ByteBuffer abandonedBuffer = ByteBuffer.allocate(4);
                Future<Integer> secondRead = client.read(abandonedBuffer);
                boolean cancelled = secondRead.cancel(false);

                System.out.println("Cancel returned: " + cancelled);
                System.out.println(
                        "Future cancelled: " + secondRead.isCancelled());

                // Do not access abandonedBuffer after cancellation.
                // Close the channel: do not retry reading on a questionable state.
                client.close();
                System.out.println(
                        "Channel open after close: " + client.isOpen());
            }
        }
    }
}
```

Compile/run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 AsyncDeadlineCancelDemo.java
java AsyncDeadlineCancelDemo
```

**Expected stdout on an environment permitting TCP loopback:**

```text
Connected: true
Wait timeout: read still pending
Read after wait timeout: X
Cancel returned: true
Future cancelled: true
Channel open after close: false
```

### Why Is This Sequence Meaningful?

- `listener.accept()` and `client.connect(address)` both use the asynchronous API; `get` in the example only makes the test sequence easy to read. In production systems, callbacks can be used to avoid blocking the coordinator thread.
- `firstRead` is pending because the server has not sent data, not because a scheduler was paused with `sleep`. The 150ms mark is only the **`get` timeout**, not an operation timeout.
- The `firstRead` Future remains usable after the `get` timeout: when the server sends `X`, the subsequent `get` call on **the same future** returns the data. That is direct proof of the difference between "stop waiting" and "operation finished."
- `secondRead.cancel(false)` marks the Future cancelled in a scenario with no incoming data. The demo **does not claim** the underlying OS read stopped; it closes the client to handle resources under a safe policy.
- `client.isOpen()` is `false` **after actively calling `close()`**. The demo does not infer channel state immediately after cancel or an operation-level timeout.
- The cancelled `ByteBuffer` is not printed/`clear`ed/returned to a pool; this avoids turning an operation-specific state into a safety assumption.

**Do not use the output to assert how every JDK/provider handles cancel**: underlying I/O cancellation behavior is implementation-specific. The demo only relies on easily verifiable coordination conditions: the server sends no data before the `get` timeout, then sends exactly one byte, and the Java-level Future reports cancelled per contract. Loopback connections may be blocked by a sandbox/firewall; in that case it is an environment error, not evidence of different I/O semantics.

## 9. How Are Deadlines Designed When Using CompletionHandler Instead of Future?

### 9.1. Callbacks Receive Success or Failure

In this form:

```java
// Illustrative code; channel, buffer, handleCompletion,
// and handleFailure are application-defined variables/methods.
channel.read(buffer, 750, TimeUnit.MILLISECONDS, null,
        new CompletionHandler<Integer, Void>() {
            @Override
            public void completed(Integer bytes, Void ignored) {
                handleCompletion(bytes);
            }

            @Override
            public void failed(Throwable error, Void ignored) {
                handleFailure(error);
            }
        });
```

The caller does not wait on `get`; the runtime invokes the callback when the operation completes or fails. If the read times out at 750ms before completion, `failed` receives `InterruptedByTimeoutException`. You must ensure both `completed` and `failed` feed into a **single terminal decision** mechanism and corresponding cleanup.

### 9.2. An Overall Deadline Does Not Emerge Merely from Having a Timeout on Read

A client may need:

```text
t0              t1           t2                  t3
|-- connect ----|-- write ---|--- read response ---|
                 everything must finish before the overall deadline
```

If each segment has a 1-second timeout while the total request budget is 1.5 seconds, a single connection could take 2–3 seconds across sequential retries. Store `deadlineNanos` in the **request context** and compute `remaining` before each operation. For connect overloads that do not accept a timeout directly, you can schedule an application timer to decide to abandon the request and **close the channel** if connecting has not finished.

A timer does not stop I/O if it only sets a flag. When the timer wins the terminal-state race, the code must act (e.g., close the channel) to release resources rather than just returning a `TimeoutException` to the caller and forgetting the socket.

### 9.3. Late Callbacks and Repeated Cleanup

A callback may arrive right before or after the business deadline. In that case:

- Do not send two responses, and do not invoke the success callback after the request has already reported a timeout.
- Do not reuse a buffer that another operation may still be managing.
- Close the channel/buffer lease at most once at the ownership level, even if both the timer and the callback pass through `finally`/cleanup.
- If the system uses a request ID, log the ID, error type, deadline, and I/O direction; do not log sensitive payloads.
- Do not block for long inside `CompletionHandler`, as it may run on a thread pool serving other operations.

A state-transition pattern:

```java
// Illustrative code: terminal is an AtomicBoolean initially false.
// Timer and callback share one request context.
if (terminal.compareAndSet(false, true)) {
    // Only the winning branch may deliver the final result to the caller.
    // If timeout/cancel: close the channel and clean up resources.
}
// The losing branch does not emit a second result; still performs appropriate cleanup.
```

You must avoid a subtle bug: the timer sets `terminal=true` but does not close the channel, while the late callback arrives and is ignored without cleaning up; in that case the socket/buffer can leak. **Terminal decision** and **resource cleanup** are related responsibilities, not substitutes for each other.

## 10. On Error: Reuse the Channel or Open a New Connection?

In practice there are three distinct decisions:

1. **Operation completed partially without error:** continue the exact remaining portion on the channel, e.g., `write` 100/500 bytes; keep the `ByteBuffer` with 400 bytes remaining.
2. **Logic/serialization error:** `ReadPendingException` indicates a read is already pending; fix concurrency/state rather than calling `read` again or tearing down the connection blindly. If the owner cannot restore the invariant, closing the channel is an acceptable option.
3. **Timeout/cancellation/transport error leaving byte state uncertain:** instead of trying to recover by calling `clear`, close the channel, release old state, and create a new channel when retry policy permits.

### 10.1. Can the Request Be Retried?

Suppose a client sends a money-transfer command; `write` completes, but `read` times out. The command on the server **may have already been applied**, while the response was lost/delayed. If the client opens a new channel and resends it as a new command, it may cause duplicate execution.

A practical design should include:

- A **request ID / idempotency key** preserved when retrying the same business intent.
- A **status lookup API** or reconciliation by request ID.
- Appropriate **deduplication/transaction** mechanisms on the server, not just checking the ID at the network layer.
- Bounded retries, exponential backoff, jitter, and an overall deadline; retry only when the contract permits.
- Distinguishing errors before the request could reach the server from errors after the server may have executed it; if indeterminable, mark **outcome unknown**.

TCP/async channels do not provide "exactly-once business action." A new channel only resolves connection infrastructure, not business logic that already ran on the other end.

### 10.2. Reopening a Channel Is Not Resuming the Same Session

A closed `AsynchronousSocketChannel` cannot be reopened; you must create a new object/channel to reconnect. The new connection has fresh TCP state. Application session, authentication, TLS handshake, transaction context, or subscriptions must be re-established depending on the protocol. Do not assume pending data from the old connection is carried over automatically.

### 10.3. Differences Between Socket Channels and File Channels

`AsynchronousFileChannel` supports asynchronous positional file I/O. Unlike `AsynchronousSocketChannel`:

- Multiple file read/write operations can be outstanding concurrently; completion order is **not guaranteed**.
- Each I/O operation takes its own `file position`; there is no shared current file position like a stream.
- `Future.get(timeout)` still only limits **waiting for the result**, and does not guarantee rolling back writes to the file.
- Closing causes outstanding operations to fail according to `AsynchronousChannel` semantics; partial file modifications written before the error may require inspection/recovery via an application protocol.
- Do not apply `AsynchronousSocketChannel`'s "one read and one write" rule verbatim to every type of asynchronous channel.

**Deadlines and cancellation are general concerns**, but I/O behavior and recoverability must be checked against the documentation of **the exact class and method**, not inferred from the generic word "asynchronous."

## 11. Safe Error-Handling Checklist for Async I/O

An operational implementation can follow this sequence:

1. **Before initiating an operation:** confirm the channel is in an appropriate state; no same-direction I/O is pending; the request still has deadline budget; allocate a dedicated buffer and record ownership.
2. **When initiating:** set an operation timeout if the API supports it; record start time (monotonic), request ID, direction, expected size, and `PENDING` state.
3. **On success:** process only after completion; read the byte count/EOF result; handle partial reads/writes and framing; update pending state; release the buffer only after no aliases/I/O remain.
4. **On `get` wait timeout:** recognize only the caller timed out while the operation may still be pending; decide to keep waiting or abandon + close; do not prematurely `clear` the buffer or issue a new operation.
5. **On timed I/O failure:** if the cause is `InterruptedByTimeoutException`, treat the channel/ByteBuffer as questionable; close the channel and use a fresh buffer when retrying.
6. **On cancel:** observe Future/callback semantics accurately; remember cancel may leave the channel in an error state or closed; do not treat cancel as a byte rollback.
7. **On `AsynchronousCloseException`/`ClosedChannelException`:** determine whether it was expected cleanup or an external error; do not reuse a closed channel.
8. **On `ReadPending`/`WritePending`:** fix concurrency logic rather than hot-retrying; enforce a single owner per read/write direction.
9. **On service shutdown:** stop accepting new requests, apply a drain deadline; after expiration, close remaining pending channels and wait for groups/executors to finish within budget.
10. **On retry:** use backoff and idempotency/reconciliation if the action has side effects; create a new channel/ByteBuffer when old state is no longer guaranteed.

## 12. Common Misconceptions

| Misconception | Reality |
|---|---|
| "When `future.get(timeout)` expires, Java automatically cancels the read/write." | No. `get` only stops the caller from waiting. |
| "`cancel(false)` rolled back the bytes just read/written." | There is no guarantee of rolling back underlying I/O; cancel behavior is implementation-dependent. |
| "`cancel(true)` definitely only interrupts one thread." | With asynchronous channels, the runtime **may close the channel** and cause other I/O to fail. |
| "`isCancelled()==true` means the ByteBuffer is safe to reuse." | No. Especially when the underlying operation has not necessarily stopped, you must manage lifetime safely. |
| "`InterruptedByTimeoutException` is the `TimeoutException` from `Future.get`." | They are two different mechanisms: operation timeout vs. wait timeout. |
| "Read timed out, but `isOpen()==true`, so I can read again normally." | The channel may be in an **implementation-specific error state**; a subsequent read may throw a runtime exception. |
| "A timed-out read cannot have received any bytes." | Not guaranteed; the buffer may be in an undefined state after timed I/O. |
| "`ByteBuffer.clear` wipes the data and cancels I/O." | No. It only resets buffer indices; it does not cancel the operation. |
| "Every async channel only allows one outstanding read and one outstanding write." | That rule applies to `AsynchronousSocketChannel`; file channels have different semantics. |
| "Future cancelled means the server definitely did not execute the request." | No. The server may have already received and processed the payload; the business outcome may be unknown. |
| "`close` guarantees client and server know the same business outcome." | No. Close is a resource/connection operation, not a substitute for application acknowledgment. |
| "Just retry whenever you see `ReadPendingException`." | This is usually a bug in managing outstanding I/O; hot retrying makes it worse. |
| "The timer/callback just needs to mark terminal state." | You must also clean up the channel, buffer, and pending operations, even when callbacks arrive late. |

## 13. Self-Check Questions and Answers

**Q1.** After `channel.read(dst)` returns a Future, `future.get(100, MILLISECONDS)` throws `TimeoutException`. Can you call `dst.clear()` and start another read immediately?

**Answer:** No. A Future wait timeout does not stop I/O; the first read may still be pending and using `dst`. A new read in the same direction can also trigger `ReadPendingException`. You must preserve ownership, wait for completion, or close/clean up the channel when abandoning.

**Q2.** A timeout attached directly to `AsynchronousSocketChannel.read(dst, t, unit, attachment, handler)` typically reports which exception type?

**Answer:** `InterruptedByTimeoutException` in the `failed` callback. After a timeout, the channel and buffer states may be undefined; do not assume retrying a read on the same channel is safe.

**Q3.** If `future.cancel(true)` returns true, is the channel guaranteed to be closed?

**Answer:** No. The API states the runtime **may close the channel**; underlying I/O cancellation is implementation-specific. Do not treat a `true` return value as proof that no bytes were transferred.

**Q4.** A `read` was cancelled, yet `isOpen()==true`. Can you reuse the same buffer and connection as before?

**Answer:** Not by default. Cancellation can leave an error state and the buffer may still be affected. The simple policy is to close the channel, discard the questionable buffer, and open a new connection if needed.

**Q5.** When `Future.get` throws `ExecutionException`, is that the root I/O cause?

**Answer:** `ExecutionException` is a wrapper; inspect `getCause()` to identify `IOException`, `AsynchronousCloseException`, or another cause.

**Q6.** Does `AsynchronousSocketChannel` allow one read and one write concurrently? What about two reads at the same time?

**Answer:** One read and one write can run concurrently; two outstanding reads are not allowed. Calling a second read before the first finishes throws `ReadPendingException`.

**Q7.** A read Future times out at the caller, and a few seconds later `get` on **the same Future** returns data. Is that a contradiction?

**Answer:** No. The initial timeout was only the wait expiring; the underlying read can complete later. The `AsyncDeadlineCancelDemo` example illustrates this exact behavior.

**Q8.** After a write to the server succeeds, reading the response times out. Can you conclude the server has not committed?

**Answer:** No. The business state may be unknown. You need a request ID, idempotency, and a reconciliation/status-query mechanism instead of blind retries.

**Q9.** If the intrinsic timeout parameter passed to `AsynchronousSocketChannel.read` is `0`, does the read time out immediately?

**Answer:** No. For this class's timeout overloads, a value **≤ 0** means the operation has **no timeout**. Check the deadline before calling instead of clamping negative remaining time to 0.

**Q10.** A success callback and a timeout timer race with each other. How do you avoid emitting two results?

**Answer:** Use a state machine or atomic terminal decision so only one branch wins; at the same time, clean up resources properly in both winning and losing branches so late callbacks do not cause leaks.

## 14. Key Takeaways and API References

**Four points to remember:**

1. **`Future.get(timeout)` only limits wait time**, and does not cancel I/O by default.
2. **Timed `AsynchronousSocketChannel.read/write` may end with `InterruptedByTimeoutException`**, and the state of the channel/**ByteBuffer** afterward may be undefined.
3. **`Future.cancel` does not guarantee rollback or that underlying I/O has stopped**; `cancel(true)` may also close the channel. `isOpen()` is not sufficient to judge a channel healthy after an error.
4. **Deadline design must pair with state, ownership, cleanup, and business idempotency.** Once it is uncertain which bytes were transferred or processed, close the questionable channel and open a new connection rather than blindly reusing buffers.

Official Java SE 17 documentation:

- [AsynchronousChannel — Cancellation and close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannel.html)
- [AsynchronousSocketChannel — Timed read/write, error state, pending ops](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html)
- [AsynchronousFileChannel — Multiple outstanding operations, buffers](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html)
- [Future — get(timeout), cancel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [ByteBuffer — position, limit, ownership](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)