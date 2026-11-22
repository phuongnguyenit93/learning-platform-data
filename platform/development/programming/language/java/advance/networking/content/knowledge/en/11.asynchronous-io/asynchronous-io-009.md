# Closing Channels, Handling Failed Callbacks, and Orderly Group Termination in Java Asynchronous I/O

## Objectives

In Java NIO.2, an I/O operation may have been **initiated but not yet completed** when the application begins shutting down the service. If `AsynchronousSocketChannel` is closed too early, pending `read`/`write` operations may enter `CompletionHandler.failed(...)`. If `AsynchronousChannelGroup.shutdown()` is called and the application assumes all sockets have closed automatically, it may wait forever at `awaitTermination(...)`. If a failed callback re-initiates a new `accept` or `read` while the server is stopping, the program can easily produce repeated errors, leak resources, or fail to terminate.

This lesson thoroughly explains three interconnected topics:

1. **Closing individual channels**: distinguishing between stopping new connections, letting current tasks finish, one-way half-close, `close()` forcing pending operations, and callbacks reflecting failure.
2. **Handling failed callbacks**: classifying expected shutdown errors versus real errors that must be reported; never skipping cleanup, never letting callbacks re-register work after stopping, and never reusing a `ByteBuffer` while an operation has not finished.
3. **Terminating an `AsynchronousChannelGroup` in the right order**: stop admission → drain in-flight work within a deadline → close channels → `shutdown()` → `awaitTermination()` → only use `shutdownNow()` when necessary; recording both success and failure paths.

The examples use **Java 17+**, loopback TCP, and the `java.nio.channels` APIs. Three standalone programs demonstrate the exact behaviors: a callback failing due to channel close; group shutdown not closing channels automatically; and stopping the listener first, completing the exchange, and only then terminating the group.

## 1. The Big Picture: Channel, Operation, Callback, and Group

Key classes:

- `AsynchronousServerSocketChannel`: asynchronous TCP listener; `accept()` completes when a connection arrives or fails.
- `AsynchronousSocketChannel`: asynchronous TCP socket; `connect`, `read`, `write` may complete at a different time from when they were invoked.
- `CompletionHandler<V,A>`: receives one of two outcomes—**`completed(V result, A attachment)`** or **`failed(Throwable exc, A attachment)`**—for an operation.
- `Future<V>`: an alternative way to track results, wait with `get()`, handle `ExecutionException`, `CancellationException`, `TimeoutException`, or request `cancel(...)`.
- `AsynchronousChannelGroup`: a group that manages resources and completion dispatch mechanisms for associated asynchronous channels; the group has a thread pool serving completion handlers and certain I/O-related tasks.

```text
Lifecycle of an NIO.2 TCP service

                     AsynchronousChannelGroup
                      ┌──────────────────────┐
                      │ completion dispatch  │
                      │ group threads        │
                      └─────────────▲────────┘
                                    │ completed(...) / failed(...)
                                    │
  Listener: AsynchronousServerSocketChannel
       accept() ───────► pending operation
                             │
          accepted client ───┘
                  │
                  ▼
  Connection: AsynchronousSocketChannel
      read(ByteBuffer, attachment, handler)
                   │
             pending / completed / failed
                   │
             business handler
                   │
      write(ByteBuffer, attachment, handler)
                   │
             pending / completed / failed

  On shutdown:
  STOP_ACCEPTING → DRAIN_IN_FLIGHT → CLOSE_CHANNELS
                 → GROUP_SHUTDOWN → AWAIT_TERMINATION
                 → FORCED_CLOSE if deadline exceeded
```

**A channel can have many operations over its lifetime, but that does not mean every operation is allowed concurrently.** `AsynchronousSocketChannel` allows at most **one outstanding read** and **one outstanding write** concurrently on the same channel. Calling another read while the previous read has not completed can throw `ReadPendingException`; similarly `WritePendingException`. `AsynchronousServerSocketChannel` allows only one outstanding `accept` at a time; calling another causes `AcceptPendingException`.

Channels may be used from multiple threads, **but `ByteBuffer` itself is not thread-safe**. Do not modify `position`/`limit`, release, or reuse the buffer of a pending operation just because the `read/write` method has returned. With callbacks, buffer processing normally begins **once the operation has completed**.

### Differences from Selector

Readiness-based NIO `Selector` requires an event loop to inspect `OP_READ/OP_WRITE` and then invoke non-blocking I/O itself. In NIO.2, you **initiate an asynchronous operation** and receive a callback/Future when the operation completes or fails. `AsynchronousChannelGroup` is not a `Selector` exposed for the application to arbitrarily pull `selectedKeys()`; closing a group is also not as simple as closing a Selector.

## 2. Two Ways to Receive Results: Future and CompletionHandler

### 2.1. Future: Simple for Bounded Experiments

```java
// Illustrative snippet; channel and buffer variables must be created externally.
Future<Integer> pending = channel.read(buffer);
int count = pending.get(3, java.util.concurrent.TimeUnit.SECONDS);
```

This is an **illustrative snippet**, not a standalone program. `get(timeout)` waits up to a duration for the result. If it times out, `TimeoutException` only indicates that **the waiting thread** has not received a result yet; it **does not automatically cancel** the I/O operation and does not prove the peer has disconnected.

If the operation completes with failure, `Future.get()` throws `ExecutionException`, and the I/O cause is in `getCause()`. If the Future itself was cancelled, `get()` throws `CancellationException`. If the waiting thread is interrupted, `get()` may throw `InterruptedException`; this is the waiting thread's state and must not be assumed to mean I/O was cancelled.

**Note:** calling `get()` immediately on every operation forces the calling thread to wait, reducing the benefit of the callback model in large servers. However, `Future` is well-suited for writing **deterministic experiments** and explaining lifecycles, as in the examples at the end of this lesson.

### 2.2. CompletionHandler: Notified When the Operation Finishes

```java
// Illustrative snippet: channel and buffer are ready, callback manages cleanup.
channel.read(buffer, requestId, new CompletionHandler<Integer, String>() {
    @Override
    public void completed(Integer bytesRead, String id) {
        // bytesRead > 0: consume newly read bytes.
        // bytesRead == -1: EOF; handle end of read stream.
    }

    @Override
    public void failed(Throwable error, String id) {
        // Log error by id, complete failed state, cleanup.
    }
});
```

This is an illustrative snippet; `import java.nio.channels.CompletionHandler` and full variable context are required. `A` is the attachment type, which lets you attach `requestId`, `connectionState`, or a state object to the operation. `V` is the result type: `Integer` for read/write, `Void` for connect, `AsynchronousSocketChannel` for accept.

Callback methods should **complete quickly**. According to the Javadoc, completion handlers run on threads belonging to the group; under certain conditions when an operation completes immediately and the calling thread is already a group thread, the handler **may be invoked directly on that thread**. Never assume each callback spawns a new thread or that a callback can block indefinitely without affecting other operations.

### 2.3. Operation Completion Is Not Business Completion

- `write.completed(n)` proves a chunk of `n` bytes was accepted for writing by the operation; it does **not** prove the peer read the message or committed a transaction.
- `read.completed(-1)` is a **normal EOF of the read side** after any remaining data, not the same category as `failed(IOException)`.
- `read.completed(0)` can occur under certain conditions; do not treat it as an empty message or guaranteed progress.
- `connect.completed(null)` confirms the TCP connect operation completed, **not** that the server processed a request.
- `accept.completed(channel)` only confirms a connection was accepted, not that the subsequent communication session will succeed.

An application that needs business confirmation must define request/response/ack at the proper protocol layer, rather than treating an I/O callback as a business acknowledgment.

## 3. Closing Individual Channels: What Happens to Pending Operations?

`AsynchronousChannel` extends `Channel` and `AutoCloseable`. For `AsynchronousSocketChannel` and `AsynchronousServerSocketChannel`:

- `close()` closes the **local channel**. If there are outstanding asynchronous operations, per the `AsynchronousChannel` contract, those operations **complete with failure via `AsynchronousCloseException`**.
- After the channel is closed, attempting to initiate new I/O fails with a `ClosedChannelException` cause, according to the specific API method and error-reporting mechanism.
- `close()` does not guarantee that all **callbacks have finished running** the moment it returns; tracking/latch/Future or group-level `awaitTermination` is needed to wait for already-initiated callbacks.
- `isOpen() == false` only reflects that the channel is closed; it does **not** prove application cleanup, metrics, responses, or callbacks have completed.
- Try-with-resources ensures the channel is closed upon exiting scope, but it does not turn all pending operations into "successfully processed."

### 3.1. Three Crucial Race Cases

```text
Case A — operation is pending:
  read() ----------- pending ------------ [close()]
                           \______________ failed(AsynchronousCloseException)

Case B — operation completes before close:
  read() ---- completed(bytes) ---- [close()]
  => do not overwrite an already-completed operation as a close failure

Case C — initiated after close:
  [close()] ---- read()
  => no valid new I/O; may fail with ClosedChannelException
```

When `close()` races with an operation just completing, you must handle the **actual observed outcome**, not assume every callback arriving after shutdown starts is a failure. A response may have been partially sent before an error occurred; therefore, side effects cannot be automatically replayed if the protocol lacks idempotency.

### 3.2. Half-Close Is Not Closing the Entire Channel

On a connected `AsynchronousSocketChannel`:

- `shutdownOutput()` terminates the **write side**: subsequent writes are rejected; the read side can still be used to receive responses.
- `shutdownInput()` terminates the **local read side**; subsequent reads typically yield EOF per the API, though the effect on an outstanding read is **system-dependent**.
- `close()` closes the channel, affecting pending operations as well.
- When a write is still pending, the Javadoc states the effect of `shutdownOutput()` on an outstanding write is **unspecified**. For graceful completion, wait for writes to finish before half-closing or closing per the application contract.

Example of an EOF-based request–response design: send the full request, wait for write completions, call `shutdownOutput()`, and continue reading the response. Never call `close()` after the first write if you still need to read the reply.

### 3.3. Self-Induced Close Errors Are Normal, but Do Not Silence All Errors

If operations intentionally close the listener during service shutdown, a pending `accept` may enter the `failed(...)` callback with `AsynchronousCloseException`. That can be an **expected termination** in the STOPPING state, not requiring an infrastructure incident alert.

However, `AsynchronousCloseException` while **RUNNING** may suggest another thread accidentally closed the socket, a timeout/cancellation, or a lifecycle bug. Therefore, log **shutdown state, connection ID, operation, request ID, and cause**, rather than filtering solely by exception class.

## 4. `failed(Throwable,A)` Must Complete the Failure Path

Do not write empty callbacks:

```java
// WRONG: loses the cause and leaves the task hanging in the system.
@Override
public void failed(Throwable exc, ConnectionState state) {
}
```

This is an **anti-pattern** example, not standalone runnable code. When an operation fails, there are at least four things to consider: **marking state**, **notifying waiters**, **releasing resources**, and **classifying logs/metrics**.

### 4.1. Classifying Errors by Context

| Observed Form | Common Meaning | Appropriate Behavior |
|---|---|---|
| `AsynchronousCloseException` with STOPPING flag set | Pending operation was closed along with the channel | May be treated as expected shutdown, but still complete the task and clean up |
| `AsynchronousCloseException` while RUNNING | Channel was closed while operation was waiting | Investigate lifecycle/race; do not assume normal |
| `ClosedChannelException` | Used an already-closed channel or completion reported closed | Do not reuse channel; check state and who closed it |
| `InterruptedByTimeoutException` | Timeout on async API's timed `read/write` overload | Close or remove channel from pool per policy; buffer/I/O state may be unspecified |
| `ReadPendingException` / `WritePendingException` | Initiated two reads or two writes concurrently on one socket | In-flight operation management bug; serialize per direction |
| `AcceptPendingException` | Two outstanding accepts on the same listener | Only re-arm accept after the previous accept finishes |
| `ShutdownChannelGroupException` | Attempted to create a channel in a shut-down group or cannot dispatch callback because group terminated | Stop accepting new work; check shutdown order and ownership |
| Other `IOException`, e.g. remote reset | Real I/O error, peer may have disconnected | Complete request as failed; handle retry per protocol |
| Exception thrown by **code inside callback** | Application handling bug inside callback | Catch and log at callback boundary, complete task, and clean up |

**`failed` receives `Throwable`, not just `IOException`.** Do not arbitrarily swallow every `Throwable`; at the same time, ensure cleanup runs in the failure branch. For severe errors like `Error`, have an operational and detection policy—never assume the system is safe to keep serving.

### 4.2. State Model for a Connection

```text
NEW → CONNECTING → ACTIVE → DRAINING → CLOSED
           │         │        │
           └─────────┴────────┴────► FAILED → CLOSED

Each request:
PENDING → COMPLETED
       └→ FAILED / CANCELLED / TIMED_OUT

An operation finishes along one terminal path, while
a connection may own multiple distinct operations / callbacks.
```

When implementing across multiple threads, use synchronization, locks, or `AtomicBoolean.compareAndSet` to ensure actions like "notify client, remove from registry, decrement active count" happen **logically once**. That does not replace receiving each operation's outcome; it prevents a timeout path and a callback from completing the same request twice.

### 4.3. Conceptually Safe Cleanup Callback Pattern

```java
// Java pseudocode: ConnectionContext, finishFailure, and closeQuietly
// are application components to be defined; NOT a standalone program.
@Override
public void failed(Throwable exc, ConnectionContext ctx) {
    try {
        if (!ctx.stopping.get()) {
            ctx.logger.error("I/O failed id=" + ctx.id, exc);
        } else {
            ctx.logger.debug("I/O stopped id=" + ctx.id, exc);
        }
        ctx.finishFailure(exc); // idempotent: notify pending request once.
    } finally {
        ctx.closeQuietly();
    }
}
```

Separate **recording/completing the task** from **closing the channel**, because `close` can trigger other failure callbacks. A callback should not hold a lock and wait for another callback on the same thread pool; that is a classic deadlock path.

### 4.4. Do Not Re-Arm During Shutdown

An asynchronous accept loop might follow this pattern:

```java
// Pseudocode: rearmAccept() and onAccepted() are application methods.
public void completed(AsynchronousSocketChannel peer, State state) {
    if (state.stopping.get()) {
        closeQuietly(peer);
        return;
    }
    rearmAccept(); // Only when listener is still open and app still accepts new work.
    onAccepted(peer);
}

public void failed(Throwable error, State state) {
    if (state.stopping.get()) {
        state.acceptStopped.countDown();
        return;
    }
    logUnexpectedAcceptFailure(error);
    // Only retry/re-arm under a backoff policy, avoiding infinite loops.
}
```

This snippet is **not standalone**. Key point: once the server has requested a stop, do not keep calling `listener.accept(...)` from the `failed` callback. If an accept succeeded right during shutdown while the app is no longer taking new work, **close the accepted channel immediately** to prevent leaks; never treat `completed` as always meaning "keep serving."

## 5. The Truth About Timeouts and Cancellation

Two kinds of timeouts are often confused:

**Waiter timeout on Future:** `future.get(2, SECONDS)` throws `TimeoutException` when the caller waits past the deadline. The asynchronous operation may still be running. If the app wants to terminate it, it needs an explicit policy for cancel/close and waiting for cleanup; do not reuse the buffer immediately.

**I/O-level timeout:** the `AsynchronousSocketChannel.read/write(..., long timeout, TimeUnit unit, ..., handler)` overload can complete with failure via `InterruptedByTimeoutException`. The JDK documentation warns that after a timeout, if the system cannot guarantee no bytes were read/written, the channel or I/O direction may enter an **implementation-specific error state**, and the associated `ByteBuffer` state is **unspecified**. For operations with important side effects, close the connection and use protocol idempotency/responses to determine state instead of continuing to write as if nothing happened.

**`Future.cancel(boolean)`:** requests cancellation of the Future. It may cause `Future.get()` to throw `CancellationException`, but whether underlying I/O stops depends on the implementation; `cancel(true)` may result in closing the channel. The Javadoc also advises caution with the buffer of a cancelled operation while the channel remains open.

Never claim:

- "`Future.get(timeout)` expired so the read cancelled itself."
- "`cancel(false)` guarantees no bytes were ever read/written."
- "`cancel(true)` only interrupts the callback thread and keeps the socket guaranteed safe."
- "`ByteBuffer.position` is still reliable after any timeout/cancellation."

When a client sends a non-idempotent operation, a Java-layer timeout only tells you **no reliable result was received**, not that the server definitely did not process it. Retries require a request ID and proper dedup/idempotency mechanisms, not reliance on how the channel was closed.

## 6. `AsynchronousChannelGroup`: Shutdown Differs from Closing Channels

An `AsynchronousChannelGroup` groups channels and a thread pool that dispatches callbacks. A group is created explicitly, for example:

```java
// Illustrative example: where the service lifecycle is managed.
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(4, Thread::new);
AsynchronousServerSocketChannel listener =
        AsynchronousServerSocketChannel.open(group);
AsynchronousSocketChannel client =
        AsynchronousSocketChannel.open(group);
```

This is an illustrative snippet requiring `import java.nio.channels.*` and full cleanup. A group can be created via `withFixedThreadPool`, `withCachedThreadPool`, or `withThreadPool`. Channels opened with `open(group)` are bound to the specified group; channels opened without a group typically use the JVM's default group.

### 6.1. Key Comparison Table

| API | What Does It Do? | What Does It NOT Guarantee? |
|---|---|---|
| `group.shutdown()` | Marks the group as shut down; rejects new channels bound to the group; initiates orderly shutdown | **Does not automatically close all open channels**, does not force pending operations to finish |
| `group.isShutdown()` | Tells whether the group has been marked shut down | Does not mean resources have been released |
| `group.isTerminated()` | Checks whether the group and its associated thread pool have terminated | Not per-business-request state, does not replace `Future`/state tracking |
| `group.awaitTermination(t,u)` | Waits for the group to actually terminate or for timeout/interrupt | **Does not proactively close sockets**; may return false because channels remain open |
| `group.shutdownNow()` | Requests forceful shutdown, closing **all open channels in the group** | Does **not** guarantee running callbacks are interrupted/cut short; still need to await termination |
| `channel.close()` | Closes the individual channel; outstanding operations fail per contract | Does not stop the group if other channels/callbacks remain |

The Javadoc specifies that a group terminates orderly when **all channels bound to the group have closed**, **all active completion handlers have finished running**, and the group's resources have been released. `shutdown()` marks the state, while `awaitTermination` merely waits; the "close all channels" event does not happen automatically just because shutdown was called.

### 6.2. `shutdownNow()` Is a Last Resort, Not the Graceful Default

`shutdownNow()` performs the shutdown behavior plus closing all remaining open channels in the group as if `close` were called on them. Pending operations may enter `failed(AsynchronousCloseException)`. This method **does not attempt to stop/interrupt currently executing completion handlers**; the group is still only considered terminated after active handlers finish and resources are released.

If a callback contains external blocking I/O, an infinite loop, or waits on a completion that needs the same group thread, `shutdownNow()` is not a "kill switch" guaranteeing immediate termination. Callbacks must be designed to be **short, non-blocking indefinitely, responsive to stop flags**, and observable.

### 6.3. Do Not Accidentally Shut Down a Shared Group

- Channels created without passing a group use the JVM's **default asynchronous channel group**; a service should not treat it as its own exclusive group if multiple modules share it.
- If passing an `ExecutorService` to `withThreadPool(...)` or `withCachedThreadPool(...)`, the group **manages the lifecycle** of that executor. The documentation emphasizes that the executor should be dedicated exclusively to the group; shutting down the executor independently from another component can lead to unspecified behavior.
- If a service manages multiple independent groups, it must track **which channel belongs to which group** and who is responsible for terminating it. Shutting down service A's group must not unexpectedly break service B's callbacks.

## 7. Proper Graceful Shutdown Order

Define four clear states:

```text
RUNNING
  │ stop requested
  ▼
STOPPING_ADMISSION
  - set stopping=true; prevent accepting/submitting new work
  - close listener; pending accept may fail (expected)
  │
  ▼
DRAINING
  - wait for accepted requests, queued writes, and callbacks to finish
  - create no new requests; bounded deadline
  │
  ├── drain succeeded ──────────────────────┐
  │                                         │
  └── deadline exceeded → mark aborted ─────┤
                                            ▼
CLOSING_CHANNELS
  - close remaining accepted/client channels owned by service
  - fail pending requests if needed
  │
  ▼
GROUP_SHUTDOWN
  - group.shutdown()
  - group.awaitTermination(timeout, ...)
  │
  ├── terminated -> STOPPED
  │
  └── not terminated -> group.shutdownNow()
                        -> final awaitTermination
                        -> log/alert if still incomplete
```

The **drained** condition should not be just "sent some bytes" or "no new callbacks seen right now." In a server, track at least **active connections**, **in-flight request count**, **pending outbound buffers/writes**, **running business tasks**, and **callback completion**.

Recommended sequence:

1. **Block admission first.** Set the lifecycle flag, prevent new accept registrations, and stop accepting new business messages. Close `AsynchronousServerSocketChannel` to cancel any pending accept; the `failed` callback must recognize this as expected shutdown.
2. **Handle connections accepted in a race with stop.** If `accept.completed(peer)` runs after the STOPPING flag is set, close `peer` and serve no new requests.
3. **Drain in-flight work with a deadline.** Allow connections currently executing valid requests to finish and send responses, including handling partial writes. Only after all requests/responses complete should channels close normally.
4. **Clean up accepted channels.** For completed sessions, close the channel. For timed-out sessions, mark failed/cancelled, close the channel, and release registries/buffers once operations have completed/failed.
5. **Terminate the group.** Call `group.shutdown()`, then `group.awaitTermination(...)` from a **shutdown coordinator thread outside the callback pool**.
6. **Escalate if needed.** If the deadline expires, call `group.shutdownNow()`, wait for a bounded extra period, and log an alert if it still has not terminated. Never promise that a forced shutdown still delivers all responses.

### Are Other Orders Valid?

You can call `group.shutdown()` **after stopping admission while channels are still open**, because shutdown does not close them automatically. However, you must be certain that running callbacks **do not need to create new channels in the group**, and a pending accept does not place a new accepted channel into an already-shut-down group. For ease of review, this lesson recommends **stop accept → drain → close sockets → shutdown group**.

**Never wait for termination immediately while many channels remain open with no one responsible for closing them**, because the group may never reach the termination condition.

### Do Not Call `awaitTermination` Inside the Group's Own Callback

If a callback running on a group thread calls `group.awaitTermination(...)` and waits for the group to terminate, that callback itself is **an active handler**. It can prevent the termination condition from ever being met or starve other callbacks of threads. Use a separate **shutdown coordinator thread** to wait and aggregate results.

## 8. Java 17+: Closing a Channel During Pending Read, Observing `failed`

This standalone program creates a TCP listener and a client on loopback, accepting a server-side channel. It **initiates a pending read** without **sending any bytes**, then closes the server-side channel. The callback must complete the failure path. `CountDownLatch` makes main wait for the callback instead of concluding as soon as `close` returns.

**File `AsyncCloseCallbackDemo.java`:**

```java
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class AsyncCloseCallbackDemo {
    public static void main(String[] args) throws Exception {
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(2, Thread::new);
        try {
            try (AsynchronousServerSocketChannel listener =
                         AsynchronousServerSocketChannel.open(group).bind(
                                 new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
                 AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open(group)) {
                Future<AsynchronousSocketChannel> pending = listener.accept();
                client.connect(listener.getLocalAddress()).get(3, TimeUnit.SECONDS);
                try (AsynchronousSocketChannel peer =
                             pending.get(3, TimeUnit.SECONDS)) {
                    CountDownLatch callbackDone = new CountDownLatch(1);
                    AtomicReference<Throwable> failure = new AtomicReference<>();
                    AtomicBoolean successfulRead = new AtomicBoolean();

                    peer.read(ByteBuffer.allocate(32), "request-1",
                            new CompletionHandler<Integer, String>() {
                                @Override public void completed(Integer count, String tag) {
                                    successfulRead.set(true);
                                    callbackDone.countDown();
                                }
                                @Override public void failed(Throwable error, String tag) {
                                    failure.set(error);
                                    callbackDone.countDown();
                                }
                            });

                    peer.close();
                    if (!callbackDone.await(3, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Callback did not finish");
                    }
                    if (successfulRead.get()
                            || !(failure.get() instanceof AsynchronousCloseException)) {
                        throw new IllegalStateException("Unexpected callback result: "
                                + failure.get());
                    }
                    System.out.println("Pending read failed: AsynchronousCloseException");
                    System.out.println("Channel open: " + peer.isOpen());
                }
            }
        } finally {
            group.shutdown();
            if (!group.awaitTermination(3, TimeUnit.SECONDS)) {
                group.shutdownNow();
                if (!group.awaitTermination(3, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Group did not terminate");
                }
            }
        }
    }
}
```

Compile/run:

```bash
javac --release 17 -encoding UTF-8 AsyncCloseCallbackDemo.java
java AsyncCloseCallbackDemo
```

Stdout **verified on a JDK supporting Java 17+**:

```text
Pending read failed: AsynchronousCloseException
Channel open: false
```

**Reading the output properly:**

1. `listener.accept()` returns a `Future`; the client connects, and the program retrieves the accepted peer.
2. `peer.read(..., callback)` starts an operation waiting for bytes. The client writes nothing, so the read has no data to complete.
3. `peer.close()` closes the channel while the read is outstanding. Per the `AsynchronousChannel` API, the operation fails with `AsynchronousCloseException`. The `failed` callback stores the cause and releases the latch.
4. `callbackDone.await(...)` waits for the callback to enter its terminal branch. If the callback does not finish within the deadline, the program throws an error instead of printing fake data.
5. Only **after** the callback finishes does the program close the remaining channels, call `group.shutdown()`, and await termination.
6. `AtomicReference`/`AtomicBoolean` are used to pass results between the callback thread and main. Main waiting on the latch provides a clear synchronization point.

This is an **experiment intentionally provoking an error**. Production code should not routinely close sockets before responses finish and treat that as graceful shutdown.

## 9. Java 17+: `group.shutdown()` Does Not Automatically Close Open Channels

The next experiment creates a group and an unconnected `AsynchronousSocketChannel`. It marks shutdown while the channel is still open, checks that the group has not terminated, then closes the channel and waits for the group to actually terminate. Being unconnected does not matter for testing the **group lifecycle**.

**File `AsyncGroupLifecycleDemo.java`:**

```java
import java.nio.channels.*;
import java.util.concurrent.*;

public class AsyncGroupLifecycleDemo {
    public static void main(String[] args) throws Exception {
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(2, Thread::new);
        AsynchronousSocketChannel channel = AsynchronousSocketChannel.open(group);
        try {
            group.shutdown();
            System.out.println("Group shutdown: " + group.isShutdown());
            System.out.println("Channel still open: " + channel.isOpen());
            System.out.println("Group terminated yet: " + group.isTerminated());

            boolean rejected = false;
            try (AsynchronousSocketChannel ignored =
                         AsynchronousSocketChannel.open(group)) {
                // Never reaches here once the group is shut down.
            } catch (ShutdownChannelGroupException expected) {
                rejected = true;
            }
            System.out.println("New channel rejected: " + rejected);
        } finally {
            channel.close();
            if (!group.isShutdown()) group.shutdown();
            if (!group.awaitTermination(3, TimeUnit.SECONDS)) {
                group.shutdownNow();
                if (!group.awaitTermination(3, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Group did not terminate");
                }
            }
        }
        System.out.println("Group terminated after close: "
                + group.isTerminated());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AsyncGroupLifecycleDemo.java
java AsyncGroupLifecycleDemo
```

Stdout **verified**:

```text
Group shutdown: true
Channel still open: true
Group terminated yet: false
New channel rejected: true
Group terminated after close: true
```

Meaning of each line:

- `group.shutdown()` enables the shutdown state; the group **does not automatically close** existing channels.
- While a channel remains open, the group does not meet the termination condition, so `isTerminated()==false`.
- A new `AsynchronousSocketChannel.open(group)` is rejected with `ShutdownChannelGroupException`. That does not mean old channels were closed.
- After `channel.close()` and a successful `awaitTermination`, the group finally terminates.
- If waiting times out, `shutdownNow()` is used as a fallback to release lingering channels; in a successful test, this branch is not needed.

Distinguish **`group.isShutdown()`** ("received the command to begin stopping") from **`group.isTerminated()`** ("released all required resources"). Having only the first state is not enough to report the service as STOPPED.

## 10. Java 17+: Stop Listener, Finish Response, Close Channels, Then Terminate Group

This is a condensed **orderly graceful** example running in a single process: one async listener, one async client, and one accepted connection on loopback.

1. Client connects; listener retrieves the accepted channel.
2. **Close the listener** right after accept, meaning stop accepting new connections.
3. Both sides exchange a short message: `PING\n` and `PONG\n`. The example uses `Future.get(timeout)` to make ordering easy to verify, without pretending to be a full non-blocking callback server.
4. `sendAll` and `readExactly` loop to handle **partial writes/reads**, never assuming a single call sends/receives all 5 bytes.
5. Close both communicating sockets, then `group.shutdown()` and `awaitTermination`.

**File `AsyncOrderlyDrainDemo.java`:**

```java
import java.io.EOFException;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.util.concurrent.*;

public class AsyncOrderlyDrainDemo {
    private static void sendAll(AsynchronousSocketChannel channel, String text)
            throws Exception {
        ByteBuffer buffer = StandardCharsets.UTF_8.encode(text);
        while (buffer.hasRemaining()) {
            channel.write(buffer).get(3, TimeUnit.SECONDS);
        }
    }

    private static String readExactly(AsynchronousSocketChannel channel, int n)
            throws Exception {
        ByteBuffer buffer = ByteBuffer.allocate(n);
        while (buffer.hasRemaining()) {
            int read = channel.read(buffer).get(3, TimeUnit.SECONDS);
            if (read == -1) throw new EOFException("Incomplete message");
        }
        buffer.flip();
        return StandardCharsets.UTF_8.decode(buffer).toString();
    }

    public static void main(String[] args) throws Exception {
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(2, Thread::new);
        try {
            try (AsynchronousServerSocketChannel listener =
                         AsynchronousServerSocketChannel.open(group).bind(
                                 new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
                 AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open(group)) {
                Future<AsynchronousSocketChannel> pending = listener.accept();
                client.connect(listener.getLocalAddress()).get(3, TimeUnit.SECONDS);
                try (AsynchronousSocketChannel serverPeer =
                             pending.get(3, TimeUnit.SECONDS)) {
                    listener.close();
                    System.out.println("Admission stopped: " + !listener.isOpen());

                    sendAll(client, "PING\n");
                    String request = readExactly(serverPeer, 5);
                    sendAll(serverPeer, "PONG\n");
                    String reply = readExactly(client, 5);
                    System.out.println("Server received: " + request.strip());
                    System.out.println("Client received: " + reply.strip());
                }
            }
        } finally {
            group.shutdown();
            if (!group.awaitTermination(3, TimeUnit.SECONDS)) {
                group.shutdownNow();
                if (!group.awaitTermination(3, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Group did not terminate");
                }
            }
        }
        System.out.println("Group terminated: " + group.isTerminated());
    }
}
```

Commands:

```bash
javac --release 17 -encoding UTF-8 AsyncOrderlyDrainDemo.java
java AsyncOrderlyDrainDemo
```

Stdout **verified**:

```text
Admission stopped: true
Server received: PING
Client received: PONG
Group terminated: true
```

**Why is this example valuable?** `listener.close()` only stops admission on the listener; **it does not automatically close the accepted peer**. Therefore, `serverPeer` still reads PING and sends PONG; the client receives the complete reply; finally, both the client socket and the accepted server socket close before the group shuts down.

**Explicitly stated limitations:** `Future.get()` makes the main thread wait step by step, so the example lacks the throughput of a production async system. In a multi-client server, you use completion handlers or a state machine so threads do not block waiting per request; you track active sessions and separate drain deadlines. A fixed 5-byte input was chosen for a deterministic test, not as general framing for all protocols. For real protocols, use length-prefix/delimiter framing, size limits, and business acknowledgments if needed.

## 11. Production Callback/Server Design: Prevent Close and Failure from Causing Leaks

The three examples above demonstrate the API contract, whereas a system serving many connections must manage more complex state.

### 11.1. Track **Connection** and **Operation** Separately

An `activeConnections` set is not enough if callback cleanup has started but not finished, or if business tasks are offloaded to worker threads. Each request/connection may need:

```text
ConnectionContext
  channel
  state = OPEN | DRAINING | CLOSING | CLOSED
  activeRead / activeWrite
  inputParser
  outboundQueue<ByteBuffer>
  outstandingRequestIds
  stopRequested
  lastActivity

ServiceContext
  listener
  asynchronousChannelGroup
  accepting = true|false
  activeConnections
  activeRequests
  pendingCallbacks
  pendingBusinessTasks
  drainDeadline
```

This is an **illustrative data schema**, not fully declared Java classes. Counters can be backed by `Phaser`, `CountDownLatch`, `CompletableFuture.allOf`, or other concurrency primitives, but must be designed not to miss events when tasks finish very fast or when new tasks appear during shutdown.

### 11.2. In-Flight Counting Must Be Consistent

A sensible logic pattern:

```text
When receiving a valid request that is allowed to be processed:
    increment activeRequests before dispatching the task.

When the request ends in success, failure, or cancellation:
    transition PENDING → TERMINAL using atomic compare-and-set.
    if this is the first terminal transition:
        decrement activeRequests exactly once.
        notify application-level Future/callback.

When stopping:
    do not increment activeRequests for new requests.
    wait until activeRequests == 0 AND pendingWrites == 0,
    then close connections.
```

If both `failed` and a timeout handler call `activeRequests.decrementAndGet()` without a state transition guard, the counter can go negative and the shutdown coordinator will draw the wrong conclusion. Conversely, if a callback throws an exception before decrementing, the group may fail to terminate logically even though sockets are closed.

### 11.3. Re-Arm Accept Based on State

`AsynchronousServerSocketChannel.accept()` allows one outstanding accept. The `completed` callback should only re-arm **after an accept finishes** and the service is still RUNNING. When stopping the service:

- Set `accepting=false` first.
- Close the listener, causing any pending accept to fail.
- In `failed`, if `accepting=false` and the failure matches a close, log at debug level and **do not re-arm**.
- If an accept completed right during stop, close the accepted peer and create no new session.
- If accept fails abnormally while RUNNING, apply a retry/backoff policy or stop with an alert; **do not** call accept in a tight infinite loop.

A common race: thread A sets STOPPING, while thread B already read the RUNNING flag and re-arms accept just as the listener is closed. Catch exceptions at the initiation/re-arm site and ensure cleanup is not missed; a lone `AtomicBoolean` flag does not make the entire check→accept sequence an atomic transaction.

### 11.4. Re-Arming Read/Write and Buffer Ownership

After `read.completed(n)`:

- If `n > 0`, switch the buffer to read mode via `flip()` and let the parser consume it; retain leftover bytes that do not yet form a complete message.
- If `n == -1`, handle EOF, finish any waiting request, or half-close the connection per protocol.
- While STOPPING, you may finish in-progress requests, but **do not accept new business requests** from the stream.
- If you want to read more, only initiate **one new read** after the previous read has completed and the channel is still open/allowed to process. Avoid `ReadPendingException`.

After `write.completed(n)`:

- If the outbound buffer still has `hasRemaining()`, initiate the **next write**.
- If the buffer is exhausted, take the next buffer from the queue.
- If the queue is empty, mark the response as fully written at the channel layer; if the connection is DRAINING, it may close per protocol.
- If `failed`, report that the request did not receive reliable confirmation, and close/clean up per policy. **Do not assume the entire response was sent just because `write.completed` fired once.**

Never return a `ByteBuffer` to a reuse pool before the read/write has completed or failed and buffer ownership is clear. A callback can run late after a shutdown request has begun.

### 11.5. Callbacks Must Not Block Each Other

The completion-handler thread pool is usually bounded. If callback A waits on a `CountDownLatch` that callback B (which must run on the same pool) needs to `countDown`, it can deadlock or starve. Offload heavy work like DB queries, large payload encoding, or blocking HTTP calls to a separate executor whose lifecycle is managed by the application; the callback quickly updates state, enqueues work/responses, and yields back to the I/O dispatcher.

However, you must manage the **shutdown order between the business executor and the async group**: do not shut down the worker pool before callbacks that need workers finish, and do not shut down the channel group before stopping admission and accounting for in-flight requests.

## 12. Common Mistakes When Terminating a Group

| Mistake | Why It Is Wrong | How to Fix |
|---|---|---|
| Calling `group.shutdown()` and ignoring open sockets | The group may never terminate | Stop admission, drain, then close each channel; then await |
| Calling `shutdownNow()` immediately on SIGTERM | Cuts off pending responses, triggers mass failed callbacks | Use a grace period/deadline before forcing |
| Calling `awaitTermination` from a completion handler itself | The active handler can prevent the group from terminating | Use a coordinator thread outside the pool |
| Re-arming `accept` in `failed` when the listener is closed | Exception/retry loop, log spam, CPU waste | Check STOPPING; do not re-arm |
| Leaving `failed` empty | Hanging requests, leaked state/counters | Log with proper context, complete request, clean up |
| Treating every `AsynchronousCloseException` as a critical error | Proactive shutdown can produce this error | Classify according to lifecycle state |
| Treating every `AsynchronousCloseException` as "normal" | Can mask bugs closing sockets while RUNNING | Only downgrade logging for intentional closes |
| Decrementing active count in both timeout and callback | Corrupted counter; double-completion | Atomic terminal state/compareAndSet |
| Reusing a buffer after `cancel(true)` | Buffer/I/O state may be unspecified | Wait for cleanup/close channel; do not reuse prematurely |
| Calling `Future.get(timeout)` and assuming I/O is cancelled | Timeout only affects waiting on the Future | Cancel/close per policy and record outcome as unknown |
| Shutting down the group's executor directly | Javadoc gives no guarantees if the pool is shut down independently | Let the group own its executor |
| Forgetting accepted sockets belong to the same group as the listener | Group still has channels so it does not terminate | Track accepted channels and close all of them |
| Treating `isOpen()==false` as all callbacks finished | Callbacks can finish after close | Synchronize callback termination and group termination |
| Having no drain deadline | Slow peers or stuck callbacks hang shutdown forever | Grace timeout, force fallback, metrics, and alerts |
| Ignoring `InterruptedException` during await | Can lose interrupt signal or continue thread improperly | Define cleanup policy, restore interrupt flag in coordinator |
| Failing to distinguish EOF `-1` from callback failure | Normal end-of-read-stream gets labeled as an error | Handle `completed(-1)` per protocol |

### Thread Interruption Must Be Intentional

`awaitTermination` can throw `InterruptedException`. If the shutdown coordinator is interrupted, the application must execute its mandatory cleanup policy (possibly force close), then **restore the interruption** with `Thread.currentThread().interrupt()` when appropriate. Do not swallow the interrupt and wait forever in an uncontrolled retry loop.

Pseudocode example:

```text
try:
    group.shutdown()
    if not group.awaitTermination(grace):
        group.shutdownNow()
        if not group.awaitTermination(forceGrace):
            alert("group still not terminated")
catch InterruptedException:
    request forced cleanup if required by policy
    restore interrupt flag before returning
```

This is pseudocode, not runnable Java syntax; real code must also handle `IOException` from `shutdownNow()`.

## 13. Verifying Shutdown with Logs and Controlled Tests

A system should not merely log "shutdown initiated." Record the final state and anything left incomplete.

### Metrics/Fields to Capture

```text
timestamp | serviceId | lifecycleState | activeConnections
          | activeRequests | pendingWrites | pendingCallbacks
          | groupShutdown | groupTerminated | remainingDeadline
          | reason | errorClass | requestId
```

To investigate a callback failure, log `operation=ACCEPT/CONNECT/READ/WRITE`, `channelId`, `cause`, `stopping flag`, and `requestId`. Never put sensitive payloads or credentials in logs.

### Verification Matrix

| Test | Expected Evidence | Valid Conclusion |
|---|---|---|
| Close socket during pending read | Callback `failed(AsynchronousCloseException)` | Channel close affects outstanding operations |
| Close listener during pending accept | Accept callback `failed` per shutdown policy | Listener stopped admission; no re-arm |
| `group.shutdown` while channels remain open | `isShutdown=true`, `isTerminated=false` | Shutdown does not close all channels automatically |
| Close all channels, callbacks finish | `awaitTermination=true` | Group terminated within deadline |
| Send request and drain before close | Complete response, then group terminated | Graceful sequence tested successfully with demo workload |
| Request pending longer than grace | Force close, callback fails, request becomes FAILED | Escalation works when time expires |
| Callback tries to re-arm after STOPPING | No new accept/read created | Lifecycle guard works |
| Race between timeout and callback completed | Pending request has only one terminal outcome | No double-complete or double-decrement |
| Partial outbound write | Entire buffer sent before close | No lost bytes from dropping unwritten tail |
| Handler throws exception in business logic | Task still marked terminal/cleaned up | No leaked active counters |

Distinguish **API tests** from **business guarantee tests**. For example, a completed `write` and the peer receiving `PONG` on loopback verifies that test path. On a real network, a disconnect after commit can leave the client unsure whether the request ran; the solution requires correlation IDs/idempotency, which cannot be inferred from callbacks alone.

## 14. Designing a Shutdown Coordinator

A production application should have a clear lifecycle manager object rather than letting individual callbacks decide when to close the group. Algorithm outline:

```text
shutdown(graceDeadline):
  if RUNNING -> STOPPING_ADMISSION via atomic transition:
      accepting = false
      close(listener)                  // accept callback marked as expected
  else:
      return or wait on existing shutdownFuture

  stop accepting new application requests
  wait until activeRequests==0 and pendingWrites==0
       OR graceDeadline reached

  for each open connection:
      if completed:
          close normally
      else:
          complete outstanding application request as failed/unknown
          close connection (may trigger failed callbacks)

  wait for terminal callbacks/cleanup (bounded)
  group.shutdown()

  if not group.awaitTermination(groupGrace):
      group.shutdownNow()
      if not group.awaitTermination(forceGrace):
          record critical incident; do not claim fully stopped

  signal shutdownFuture completion, report metrics
```

This is **not copy-paste runnable Java code**, as it omits registries, the atomic state machine, quotas, and business policies. Boundaries required for a correct implementation:

- **Stopping admission must happen once** and be visible to running callbacks.
- **Request completion must be idempotent**: timeouts, closes, and operation failures must never complete the same request twice.
- **Drain has a realistic deadline**, and must not let one slow client lock up the entire system.
- **Close happens after flushing outbound bytes when possible**, while still providing a force path for overdue requests.
- **Shut down the group after channel ownership is clear**; never wait indefinitely on the main thread or callback pool.
- **Final success** is only reported when `isTerminated()` is true or `awaitTermination` returns true. If the deadline expires, record exactly what did not finish.
- **Never drop business outcomes**: if a write/response fails but side effects may have occurred, the state must reflect "unknown," requiring a query or dedup/idempotency.

### What Scope Counts as "Graceful"?

Graceful **does not mean** every client is guaranteed to receive a successful response. It means the system:

1. Stops creating new work at the right time.
2. Attempts to finish already-accepted work within the deadline/policy.
3. Clearly reports results or indeterminate states.
4. Releases resources in a controlled order.
5. Has a forceful termination path and is verifiable when the grace period expires.

If a client stops reading data, outbound writes can stall. In that case, expiring the grace period and closing the channel is intentional behavior, not a "total shutdown failure"; however, the message must not be recorded as processed by the client without an acknowledgment.

## 15. Self-Check

**Question 1.** `AsynchronousSocketChannel.read(...)` is pending; another thread calls `close()`. Should the callback treat that as `read` returning `-1`?  
**Answer:** No. A pending read completes with failure per the `AsynchronousChannel` contract, entering `failed` with `AsynchronousCloseException`. `completed(-1)` is read-side EOF—two different paths.

**Question 2.** `group.shutdown()` has run, but an `AsynchronousSocketChannel` is still open. Must `awaitTermination` return true immediately?  
**Answer:** No. The group only terminates when its associated channels have closed, active completion handlers have finished, and resources have been released.

**Question 3.** Why should `group.shutdownNow()` not be considered a guarantee that all running callbacks stop immediately?  
**Answer:** It closes open channels, but the Javadoc does not require interrupting currently executing completion handlers. Handlers must still finish for the group to terminate.

**Question 4.** Does closing the listener automatically close all accepted client sockets?  
**Answer:** No. Accepted `AsynchronousSocketChannel` instances are separate channels; they must be managed and closed according to the connection lifecycle.

**Question 5.** While the server is STOPPING, the accept callback `failed(AsynchronousCloseException)` runs. Should `accept` be called again immediately?  
**Answer:** No. This error can be an expected consequence of closing the listener; re-arming against the lifecycle can cause an error loop. Finish stop-admission and cleanup.

**Question 6.** `Future.get(2, SECONDS)` throws `TimeoutException`. Is the operation definitely cancelled?  
**Answer:** No. Only the waiting thread timed out; underlying I/O may still be pending. Decide on cancel/close separately and do not rush to reuse the buffer.

**Question 7.** `read` with an async timeout throws `InterruptedByTimeoutException`. Can you trust `ByteBuffer.position` to accurately reflect unread bytes?  
**Answer:** Not guaranteed. The JDK warns that buffer state and the I/O direction may be unspecified in certain timeout cases.

**Question 8.** Why should `group.awaitTermination` not be called from inside a completion handler of that same group?  
**Answer:** That handler is still active, which can prevent the termination condition from being satisfied and starve other callbacks of threads. Use a separate coordinator.

**Question 9.** Can a channel have two outstanding reads without error if they are on two different threads?  
**Answer:** No. `AsynchronousSocketChannel` supports at most one outstanding read; a second read can throw `ReadPendingException`. Same for write.

**Question 10.** If `write.completed(512)` runs while the original buffer had 2,048 bytes, is it safe to close and assume the peer received the full message?  
**Answer:** Not yet. You must continue sending the remaining `ByteBuffer.hasRemaining()` bytes and, if business logic requires it, receive an acknowledgment from the other side. Write completion does not automatically guarantee the peer processed the message.

**Question 11.** Both `CompletionHandler.failed` and a timeout timer see the same incomplete request. How do you avoid decrementing the active count twice?  
**Answer:** Use an atomic terminal state, such as compare-and-set `PENDING → FAILED/TIMED_OUT`, and let only the thread that wins the transition complete the request and decrement the counter.

**Question 12.** Is it safe to use `AsynchronousChannelGroup.withThreadPool(executor)` and then call `executor.shutdownNow()` from another module?  
**Answer:** Not recommended. The executor is meant to be dedicated to the group and the group owns its lifecycle; shutting down the executor separately causes behavior not guaranteed by the Javadoc.

**Question 13.** After `close()`, does `channel.isOpen() == false` prove all callbacks have finished and the group has terminated?  
**Answer:** No. You need separate synchronization for terminal callbacks and termination conditions.

**Question 14.** A group is stuck and not terminating after shutdown; what should you check before concluding it is a JDK bug?  
**Answer:** Check for still-open channels, pending accept/read/write operations, blocked callbacks, business workers waiting on each other, state counters, executor ownership, and whether `awaitTermination` is being called from a group thread.

## 16. Practical Summary

- **`close(channel)`** directly affects outstanding operations; `failed(AsynchronousCloseException)` is an expected consequence of closing while waiting.
- **`failed(Throwable,attachment)`** must complete the failure path, clean up, and log/emit metrics by lifecycle; do not re-arm new work while STOPPING.
- **`shutdown(group)`** begins orderly shutdown but **does not automatically close all channels**. `isShutdown` and `isTerminated` are two distinct states.
- **`awaitTermination`** waits for channels to close, callbacks to finish, and resources to be released; do not call it from a callback of the same group.
- **`shutdownNow`** is the force path that closes channels, **not** a promise to interrupt running handlers.
- The easiest sequence to review: **stop admission → drain within deadline → close channels → shutdown group → await → force fallback**.
- Future timeout/cancel and callback failure must be distinguished; when an I/O outcome is unknown, **do not assume side effects failed**.
- Writing a shutdown coordinator with atomic state, in-flight tracking, deadlines, and verified group termination is far more reliable than having each callback close resources ad hoc.

### Java 17 API References

- [`AsynchronousChannel`: close/cancellation and outstanding operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannel.html)
- [`AsynchronousChannelGroup`: threading, shutdown, shutdownNow, and awaitTermination](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html)
- [`AsynchronousSocketChannel`: read/write, connect, timeout, and half-close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html)
- [`AsynchronousServerSocketChannel`: accept and pending accept](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html)
- [`CompletionHandler`: completed/failed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html)
- [`Future`: get, cancel, and asynchronous results](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
